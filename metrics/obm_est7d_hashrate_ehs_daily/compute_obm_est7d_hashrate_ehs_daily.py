#!/usr/bin/env python3
"""
compute_obm_est7d_hashrate_ehs_daily.py

Compute the Open Bitcoin Metrics estimated network hashrate series:

    obm_est7d_hashrate_ehs_daily

The default canonical series uses a 7-day trailing rolling window. If a
different window is selected with --window_days, the output series identifier
is automatically adapted, for example:

    obm_est14d_hashrate_ehs_daily

The metric is estimated from block-level difficulty and realized block
production over a trailing rolling block-timestamp window.

For each UTC date d, the default window is the trailing 7-day interval ending
at 23:59:59 UTC on date d.

For all blocks b in the window W_d:

    estimated_hashrate_hps_d =
        sum_b(difficulty_b * 2^32) / elapsed_seconds_d

where elapsed_seconds_d is the difference between the maximum and minimum
block timestamps among the blocks included in W_d.

The final value is:

    estimated_hashrate_ehs_d =
        estimated_hashrate_hps_d / 10^18

Output schema:

    date,series_id,value,unit,frequency,release_version

Important convention:

    Hashrate is not directly observed on-chain. This metric is an estimate
    inferred from difficulty and realized block production over a rolling
    block-timestamp window.
"""

from __future__ import annotations

import argparse
import base64
import bisect
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


getcontext().prec = 60

BASE_SERIES_ID_TEMPLATE = "obm_est{window_days}d_hashrate_ehs_daily"
UNIT = "EH/s"
FREQUENCY = "daily"
DEFAULT_RELEASE_VERSION = "OBM v0.1.0"
MISSING_VALUE = "NaN"

TWO_TO_32 = Decimal(2) ** Decimal(32)
HASHES_PER_EH = Decimal("1000000000000000000")


def build_series_id(window_days: int) -> str:
    """Build the canonical OBM series identifier for the selected window."""
    if window_days < 1:
        raise ValueError("window_days must be at least 1.")

    return BASE_SERIES_ID_TEMPLATE.format(window_days=window_days)


def default_output_path(window_days: int) -> Path:
    """Return the default CSV output path for the selected window."""
    return Path(f"{build_series_id(window_days)}.csv")


def parse_utc_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date {value!r}. Expected format: YYYY-MM-DD."
        ) from exc


def utc_datetime_from_date_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def utc_datetime_from_date_end(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


def utc_timestamp(dt: datetime) -> int:
    return int(dt.timestamp())


def utc_date_from_timestamp(ts: int) -> date:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


@dataclass
class RpcConfig:
    url: str
    username: Optional[str]
    password: Optional[str]
    cookie_path: Optional[Path]
    timeout: int


class BitcoinRpcClient:
    def __init__(self, config: RpcConfig) -> None:
        self.config = config
        self._auth_header = self._build_auth_header()

    def _build_auth_header(self) -> Optional[str]:
        username = self.config.username
        password = self.config.password

        if self.config.cookie_path is not None:
            cookie_path = self.config.cookie_path.expanduser()
            if not cookie_path.exists():
                raise FileNotFoundError(f"RPC cookie file not found: {cookie_path}")

            cookie_text = cookie_path.read_text(encoding="utf-8").strip()
            if ":" not in cookie_text:
                raise ValueError(f"Invalid RPC cookie file format: {cookie_path}")

            username, password = cookie_text.split(":", 1)

        if username is None and password is None:
            return None

        if username is None or password is None:
            raise ValueError(
                "Both RPC username and RPC password are required unless "
                "cookie authentication is used."
            )

        token = f"{username}:{password}".encode("utf-8")
        return "Basic " + base64.b64encode(token).decode("ascii")

    def call(self, method: str, params: Optional[List[Any]] = None) -> Any:
        payload = {
            "jsonrpc": "1.0",
            "id": "obm",
            "method": method,
            "params": params or [],
        }

        data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            self.config.url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        if self._auth_header is not None:
            request.add_header("Authorization", self._auth_header)

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                raw_response = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Bitcoin RPC HTTP error {exc.code} for method {method}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Bitcoin RPC connection error for method {method}: {exc}"
            ) from exc

        decoded = json.loads(raw_response.decode("utf-8"))

        if decoded.get("error") is not None:
            raise RuntimeError(
                f"Bitcoin RPC error for method {method}: {decoded['error']}"
            )

        return decoded["result"]

    def get_blockchain_info(self) -> Dict[str, Any]:
        return self.call("getblockchaininfo")

    def get_block_hash(self, height: int) -> str:
        return self.call("getblockhash", [height])

    def get_block(self, block_hash: str, verbosity: int = 1) -> Dict[str, Any]:
        return self.call("getblock", [block_hash, verbosity])


def get_block_time(client: BitcoinRpcClient, height: int) -> int:
    block_hash = client.get_block_hash(height)
    block = client.get_block(block_hash, verbosity=1)
    return int(block["time"])


def find_first_height_at_or_after_timestamp(
    client: BitcoinRpcClient,
    target_ts: int,
    max_height: int,
) -> int:
    low = 0
    high = max_height
    answer = max_height

    while low <= high:
        mid = (low + high) // 2
        mid_time = get_block_time(client, mid)

        if mid_time >= target_ts:
            answer = mid
            high = mid - 1
        else:
            low = mid + 1

    return answer


def find_last_height_at_or_before_timestamp(
    client: BitcoinRpcClient,
    target_ts: int,
    max_height: int,
) -> int:
    low = 0
    high = max_height
    answer = 0

    while low <= high:
        mid = (low + high) // 2
        mid_time = get_block_time(client, mid)

        if mid_time <= target_ts:
            answer = mid
            low = mid + 1
        else:
            high = mid - 1

    return answer


@dataclass(frozen=True)
class BlockMeta:
    height: int
    time: int
    date: date
    difficulty: Decimal


def parse_difficulty(value: Any, *, height: int) -> Decimal:
    try:
        difficulty = Decimal(str(value))
    except InvalidOperation as exc:
        raise RuntimeError(
            f"Invalid difficulty value at height {height}: {value!r}"
        ) from exc

    if difficulty < 0:
        raise RuntimeError(
            f"Negative difficulty value at height {height}: {difficulty}"
        )

    return difficulty


def scan_block_metadata(
    client: BitcoinRpcClient,
    *,
    scan_start_date: date,
    scan_end_date: date,
    height_margin: int,
    verbose: bool,
) -> Tuple[List[BlockMeta], Dict[str, int]]:
    info = client.get_blockchain_info()
    tip_height = int(info["blocks"])

    start_ts = utc_timestamp(utc_datetime_from_date_start(scan_start_date))
    end_ts = utc_timestamp(utc_datetime_from_date_end(scan_end_date))

    approx_start_height = find_first_height_at_or_after_timestamp(
        client, start_ts, tip_height
    )
    approx_end_height = find_last_height_at_or_before_timestamp(
        client, end_ts, tip_height
    )

    scan_start_height = max(0, approx_start_height - height_margin)
    scan_end_height = min(tip_height, approx_end_height + height_margin)

    if scan_start_height > scan_end_height:
        raise RuntimeError(
            "Computed an empty block scan interval. Check the requested dates."
        )

    if verbose:
        print(f"Chain tip height: {tip_height}", file=sys.stderr)
        print(
            f"Window-expanded date interval: "
            f"{scan_start_date.isoformat()} to {scan_end_date.isoformat()}",
            file=sys.stderr,
        )
        print(
            f"Approximate height interval: "
            f"{approx_start_height} to {approx_end_height}",
            file=sys.stderr,
        )
        print(
            f"Expanded scan interval: "
            f"{scan_start_height} to {scan_end_height}",
            file=sys.stderr,
        )

    blocks: List[BlockMeta] = []
    scanned_blocks = 0
    counted_blocks = 0

    for height in range(scan_start_height, scan_end_height + 1):
        block_hash = client.get_block_hash(height)
        block = client.get_block(block_hash, verbosity=1)

        scanned_blocks += 1

        block_time = int(block["time"])
        block_date = utc_date_from_timestamp(block_time)

        if block_date < scan_start_date or block_date > scan_end_date:
            continue

        if "difficulty" not in block:
            raise RuntimeError(
                f"Decoded block at height {height} does not contain a difficulty field."
            )

        blocks.append(
            BlockMeta(
                height=height,
                time=block_time,
                date=block_date,
                difficulty=parse_difficulty(block["difficulty"], height=height),
            )
        )
        counted_blocks += 1

    blocks.sort(key=lambda b: (b.time, b.height))

    diagnostics = {
        "tip_height": tip_height,
        "approx_start_height": approx_start_height,
        "approx_end_height": approx_end_height,
        "scan_start_height": scan_start_height,
        "scan_end_height": scan_end_height,
        "scanned_blocks": scanned_blocks,
        "counted_blocks": counted_blocks,
    }

    return blocks, diagnostics


def compute_est_hashrate_ehs(
    blocks: Sequence[BlockMeta],
    *,
    start_date: date,
    end_date: date,
    window_days: int,
    min_blocks: int,
) -> Tuple[Dict[date, Optional[Decimal]], Dict[date, int]]:
    if window_days < 1:
        raise ValueError("window_days must be at least 1.")

    if min_blocks < 2:
        raise ValueError("min_blocks must be at least 2.")

    times = [b.time for b in blocks]

    daily_hashrate: Dict[date, Optional[Decimal]] = {}
    daily_window_block_count: Dict[date, int] = {}

    for d in daterange(start_date, end_date):
        window_start_date = d - timedelta(days=window_days - 1)
        window_start_ts = utc_timestamp(utc_datetime_from_date_start(window_start_date))
        window_end_ts = utc_timestamp(utc_datetime_from_date_end(d))

        left = bisect.bisect_left(times, window_start_ts)
        right = bisect.bisect_right(times, window_end_ts)

        window_blocks = blocks[left:right]
        block_count = len(window_blocks)
        daily_window_block_count[d] = block_count

        if block_count < min_blocks:
            daily_hashrate[d] = None
            continue

        elapsed_seconds = window_blocks[-1].time - window_blocks[0].time

        if elapsed_seconds <= 0:
            daily_hashrate[d] = None
            continue

        difficulty_sum = sum((b.difficulty for b in window_blocks), Decimal("0"))
        estimated_hps = (difficulty_sum * TWO_TO_32) / Decimal(elapsed_seconds)
        estimated_ehs = estimated_hps / HASHES_PER_EH

        daily_hashrate[d] = estimated_ehs

    return daily_hashrate, daily_window_block_count


def decimal_to_string(value: Decimal, decimal_places: int = 12) -> str:
    quant = Decimal("1").scaleb(-decimal_places)
    return format(value.quantize(quant), "f")


def write_obm_csv(
    output_path: Path,
    daily_values: Dict[date, Optional[Decimal]],
    *,
    series_id: str,
    release_version: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "date",
        "series_id",
        "value",
        "unit",
        "frequency",
        "release_version",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for d in sorted(daily_values):
            value = daily_values[d]
            if value is None:
                value_str = MISSING_VALUE
            else:
                value_str = decimal_to_string(value, decimal_places=12)

            writer.writerow(
                {
                    "date": d.isoformat(),
                    "series_id": series_id,
                    "value": value_str,
                    "unit": UNIT,
                    "frequency": FREQUENCY,
                    "release_version": release_version,
                }
            )


def plot_obm_series(
    daily_values: Dict[date, Optional[Decimal]],
    output_path: Path,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "The --plot flag requires matplotlib. Install it with: "
            "python3 -m pip install matplotlib"
        ) from exc

    dates = []
    values = []

    for d in sorted(daily_values):
        value = daily_values[d]
        if value is None:
            continue
        dates.append(d)
        values.append(float(value))

    if not dates:
        raise RuntimeError("No defined hashrate observations are available to plot.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(dates, values)

    start = min(dates).isoformat()
    end = max(dates).isoformat()

    ax.set_title(
        f"Open Bitcoin Metrics: Estimated Network Hashrate "
        f"({start} to {end})"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("EH/s")
    ax.grid(True, alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def default_cookie_path() -> Path:
    return Path.home() / ".bitcoin" / ".cookie"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute OBM estimated hashrate series by scanning Bitcoin block "
            "metadata through Bitcoin Core RPC."
        )
    )

    parser.add_argument(
        "--start_date",
        required=True,
        type=parse_utc_date,
        help="Start date of output series, inclusive, in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--end_date",
        required=True,
        type=parse_utc_date,
        help="End date of output series, inclusive, in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--window_days",
        type=int,
        default=7,
        help="Trailing rolling-window length in calendar days. Default: 7.",
    )

    parser.add_argument(
        "--min_blocks",
        type=int,
        default=2,
        help=(
            "Minimum number of blocks required in a rolling window for a "
            "defined estimate. Default: 2."
        ),
    )

    parser.add_argument(
        "--rpc_url",
        default=os.environ.get("BITCOIN_RPC_URL", "http://127.0.0.1:8332"),
        help=(
            "Bitcoin Core RPC URL. Default: environment variable "
            "BITCOIN_RPC_URL or http://127.0.0.1:8332."
        ),
    )

    parser.add_argument(
        "--rpc_user",
        default=os.environ.get("BITCOIN_RPC_USER"),
        help=(
            "Bitcoin Core RPC username. Can also be supplied through "
            "BITCOIN_RPC_USER. Not needed when --cookie_path is used."
        ),
    )

    parser.add_argument(
        "--rpc_password",
        default=os.environ.get("BITCOIN_RPC_PASSWORD"),
        help=(
            "Bitcoin Core RPC password. Can also be supplied through "
            "BITCOIN_RPC_PASSWORD. Not needed when --cookie_path is used."
        ),
    )

    parser.add_argument(
        "--cookie_path",
        type=Path,
        default=None,
        help=(
            "Path to Bitcoin Core RPC cookie file. If supplied, cookie "
            "authentication takes precedence over --rpc_user and --rpc_password."
        ),
    )

    parser.add_argument(
        "--use_default_cookie",
        action="store_true",
        help=(
            "Use the default Bitcoin Core cookie path ~/.bitcoin/.cookie. "
            "Ignored if --cookie_path is supplied."
        ),
    )

    parser.add_argument(
        "--rpc_timeout",
        type=int,
        default=120,
        help="RPC timeout in seconds. Default: 120.",
    )

    parser.add_argument(
        "--height_margin",
        type=int,
        default=2016,
        help=(
            "Extra blocks scanned before and after the approximate height "
            "interval. Default: 2016."
        ),
    )

    parser.add_argument(
        "--output",
        default=None,
        type=Path,
        help=(
            "Output CSV file path. If omitted, the filename is derived from "
            "the selected window, for example obm_est7d_hashrate_ehs_daily.csv."
        ),
    )

    parser.add_argument(
        "--release_version",
        default=DEFAULT_RELEASE_VERSION,
        help=f"Dataset release version. Default: {DEFAULT_RELEASE_VERSION}.",
    )

    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate a plot of the exported series.",
    )

    parser.add_argument(
        "--plot_output",
        default=None,
        type=Path,
        help=(
            "Output path for the plot. If omitted and --plot is used, "
            "the plot is saved next to the CSV file with .png extension."
        ),
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress diagnostic messages printed to stderr.",
    )

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        if args.start_date > args.end_date:
            raise ValueError("--start_date must be earlier than or equal to --end_date.")

        if args.window_days < 1:
            raise ValueError("--window_days must be at least 1.")

        if args.min_blocks < 2:
            raise ValueError("--min_blocks must be at least 2.")

        if args.height_margin < 0:
            raise ValueError("--height_margin must be non-negative.")

        series_id = build_series_id(args.window_days)

        if args.output is None:
            output_path = default_output_path(args.window_days)
        else:
            output_path = args.output

        if args.cookie_path is not None:
            cookie_path = args.cookie_path
        elif args.use_default_cookie:
            cookie_path = default_cookie_path()
        else:
            cookie_path = None

        rpc_config = RpcConfig(
            url=args.rpc_url,
            username=args.rpc_user,
            password=args.rpc_password,
            cookie_path=cookie_path,
            timeout=args.rpc_timeout,
        )

        client = BitcoinRpcClient(rpc_config)

        scan_start_date = args.start_date - timedelta(days=args.window_days - 1)
        scan_end_date = args.end_date

        blocks, diagnostics = scan_block_metadata(
            client,
            scan_start_date=scan_start_date,
            scan_end_date=scan_end_date,
            height_margin=args.height_margin,
            verbose=not args.quiet,
        )

        daily_values, daily_window_block_count = compute_est_hashrate_ehs(
            blocks,
            start_date=args.start_date,
            end_date=args.end_date,
            window_days=args.window_days,
            min_blocks=args.min_blocks,
        )

        write_obm_csv(
            output_path,
            daily_values,
            series_id=series_id,
            release_version=args.release_version,
        )

        if args.plot:
            if args.plot_output is None:
                plot_output = output_path.with_suffix(".png")
            else:
                plot_output = args.plot_output

            plot_obm_series(daily_values, plot_output)

        if not args.quiet:
            defined_count = sum(1 for value in daily_values.values() if value is not None)
            missing_count = len(daily_values) - defined_count
            min_window_blocks = min(daily_window_block_count.values()) if daily_window_block_count else 0
            max_window_blocks = max(daily_window_block_count.values()) if daily_window_block_count else 0

            print(f"Wrote {len(daily_values)} observations to {output_path}", file=sys.stderr)
            print(f"Series ID: {series_id}", file=sys.stderr)
            print(
                f"Output date range: {args.start_date.isoformat()} to {args.end_date.isoformat()}",
                file=sys.stderr,
            )
            print(
                f"Rolling window: {args.window_days} calendar days",
                file=sys.stderr,
            )
            print(
                f"Minimum blocks per window: {args.min_blocks}",
                file=sys.stderr,
            )
            print(
                f"Defined observations: {defined_count}",
                file=sys.stderr,
            )
            print(
                f"NaN observations: {missing_count}",
                file=sys.stderr,
            )
            print(
                f"Window block-count range: {min_window_blocks} to {max_window_blocks}",
                file=sys.stderr,
            )
            print(
                f"Counted blocks in expanded scan dates: {diagnostics['counted_blocks']}",
                file=sys.stderr,
            )
            print(
                f"Scanned blocks: {diagnostics['scanned_blocks']}",
                file=sys.stderr,
            )
            if args.plot:
                print(f"Wrote plot to {plot_output}", file=sys.stderr)

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
