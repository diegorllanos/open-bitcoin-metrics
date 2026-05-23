#!/usr/bin/env python3
"""
compute_obm_difficulty_eod_daily.py

Compute the Open Bitcoin Metrics end-of-day Bitcoin difficulty series:

    obm_difficulty_eod_daily

Definition:

    obm_difficulty_eod_daily reports the Bitcoin mining difficulty of the
    last block assigned to each UTC calendar day.

Output schema:

    date,series_id,value,unit,frequency,release_version

Important convention:

    Difficulty is a protocol state variable, not a flow. Therefore, this
    script reports an end-of-day observation rather than a daily sum.

    If no block is assigned to a selected UTC date, the value is written as
    NaN because there is no last block for that date under the selected
    timestamp convention.

Requirements:

    - Bitcoin Core full node
    - RPC access

Notes:

    - The metric is computed directly from decoded block metadata.
    - It does not require the OBM spent-output indexer.
    - It does not require txindex=1.
"""

from __future__ import annotations

import argparse
import base64
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
from typing import Any, Dict, Iterable, List, Optional, Tuple


getcontext().prec = 50

OBM_START_DATE = date(2009, 1, 1)
SERIES_ID = "obm_difficulty_eod_daily"
UNIT = "difficulty"
FREQUENCY = "daily"
DEFAULT_RELEASE_VERSION = "OBM v0.1.0"
MISSING_VALUE = "NaN"


# ---------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------

def tip_utc_date(client: BitcoinRpcClient, tip_height: int) -> date:
    tip_time = get_block_time(client, tip_height)
    return utc_date_from_timestamp(tip_time)

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


# ---------------------------------------------------------------------
# RPC client
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# Height search
# ---------------------------------------------------------------------

def get_block_time(client: BitcoinRpcClient, height: int) -> int:
    block_hash = client.get_block_hash(height)
    block = client.get_block(block_hash, verbosity=1)
    return int(block["time"])


def find_first_height_at_or_after_timestamp(
    client: BitcoinRpcClient,
    target_ts: int,
    max_height: int,
) -> int:
    """
    Return the first height whose block timestamp is >= target_ts, using a
    binary search. Bitcoin block timestamps are not strictly monotonic, so this
    value is only an approximate anchor and must be expanded with a height
    margin before the final scan.
    """
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
    """
    Return the last height whose block timestamp is <= target_ts, using a
    binary search. Bitcoin block timestamps are not strictly monotonic, so this
    value is only an approximate anchor and must be expanded with a height
    margin before the final scan.
    """
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


# ---------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------

def parse_difficulty(value: Any, *, height: int) -> Decimal:
    """
    Parse Bitcoin Core's difficulty field as Decimal.

    Bitcoin Core returns difficulty as a JSON number. Decimal(str(value))
    avoids binary floating-point artifacts introduced by Python.
    """
    try:
        difficulty = Decimal(str(value))
    except InvalidOperation as exc:
        raise RuntimeError(
            f"Invalid difficulty value at height {height}: {value!r}"
        ) from exc

    if difficulty <= 0:
        raise RuntimeError(
            f"Non-positive difficulty value at height {height}: {difficulty}"
        )

    return difficulty


def compute_difficulty_eod(
    client: BitcoinRpcClient,
    *,
    start_date: date,
    end_date: date,
    height_margin: int,
    verbose: bool,
) -> Tuple[Dict[date, Optional[Decimal]], Dict[date, Optional[int]], Dict[str, int]]:
    info = client.get_blockchain_info()
    tip_height = int(info["blocks"])

    tip_date = tip_utc_date(client, tip_height)

    if end_date > tip_date:
        raise ValueError(
            f"--end_date {end_date.isoformat()} is after the current chain-tip "
            f"UTC date ({tip_date.isoformat()}). The node cannot provide future "
            "observations."
        )

    start_ts = utc_timestamp(utc_datetime_from_date_start(start_date))
    end_ts = utc_timestamp(utc_datetime_from_date_end(end_date))

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
            f"Approximate height interval: "
            f"{approx_start_height} to {approx_end_height}",
            file=sys.stderr,
        )
        print(
            f"Expanded scan interval: "
            f"{scan_start_height} to {scan_end_height}",
            file=sys.stderr,
        )

    daily_last_height: Dict[date, Optional[int]] = {
        d: None for d in daterange(start_date, end_date)
    }
    daily_difficulty: Dict[date, Optional[Decimal]] = {
        d: None for d in daterange(start_date, end_date)
    }

    scanned_blocks = 0
    counted_blocks = 0

    for height in range(scan_start_height, scan_end_height + 1):
        block_hash = client.get_block_hash(height)
        block = client.get_block(block_hash, verbosity=1)

        scanned_blocks += 1

        block_time = int(block["time"])
        block_date = utc_date_from_timestamp(block_time)

        if block_date < start_date or block_date > end_date:
            continue

        if "difficulty" not in block:
            raise RuntimeError(
                f"Decoded block at height {height} does not contain a difficulty field."
            )

        difficulty = parse_difficulty(block["difficulty"], height=height)

        previous_height = daily_last_height[block_date]

        # "End of day" is interpreted as the last block by chain height among
        # the blocks assigned to that UTC date. This avoids relying on the
        # within-day ordering of non-monotonic block timestamps.
        if previous_height is None or height > previous_height:
            daily_last_height[block_date] = height
            daily_difficulty[block_date] = difficulty

        counted_blocks += 1

    diagnostics = {
        "tip_height": tip_height,
        "approx_start_height": approx_start_height,
        "approx_end_height": approx_end_height,
        "scan_start_height": scan_start_height,
        "scan_end_height": scan_end_height,
        "scanned_blocks": scanned_blocks,
        "counted_blocks": counted_blocks,
    }

    return daily_difficulty, daily_last_height, diagnostics


# ---------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------

def decimal_to_string(value: Decimal, decimal_places: int = 12) -> str:
    quant = Decimal("1").scaleb(-decimal_places)
    return format(value.quantize(quant), "f")


def write_obm_csv(
    output_path: Path,
    daily_values: Dict[date, Optional[Decimal]],
    *,
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
                    "series_id": SERIES_ID,
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
        raise RuntimeError("No defined difficulty observations are available to plot.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(dates, values)

    start = min(dates).isoformat()
    end = max(dates).isoformat()

    ax.set_title(
        f"Open Bitcoin Metrics: End-of-Day Mining Difficulty "
        f"({start} to {end})"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("difficulty")
    ax.grid(True, alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def default_cookie_path() -> Path:
    return Path.home() / ".bitcoin" / ".cookie"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute obm_difficulty_eod_daily by scanning Bitcoin blocks "
            "through Bitcoin Core RPC."
        )
    )

    parser.add_argument(
        "--start_date",
        required=True,
        type=parse_utc_date,
        help="Start date, inclusive, in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--end_date",
        required=True,
        type=parse_utc_date,
        help="End date, inclusive, in YYYY-MM-DD format.",
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
        default=288,
        help=(
            "Extra blocks scanned before and after the approximate height "
            "interval. Default: 288."
        ),
    )

    parser.add_argument(
        "--output",
        default="obm_difficulty_eod_daily.csv",
        type=Path,
        help="Output CSV file path.",
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

        if args.start_date < OBM_START_DATE:
            raise ValueError(
                f"--start_date must be on or after {OBM_START_DATE.isoformat()} "
                "for OBM daily difficulty exports."
            )

        if args.height_margin < 0:
            raise ValueError("--height_margin must be non-negative.")

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

        daily_values, daily_last_heights, diagnostics = compute_difficulty_eod(
            client,
            start_date=args.start_date,
            end_date=args.end_date,
            height_margin=args.height_margin,
            verbose=not args.quiet,
        )

        write_obm_csv(
            args.output,
            daily_values,
            release_version=args.release_version,
        )

        if args.plot:
            if args.plot_output is None:
                plot_output = args.output.with_suffix(".png")
            else:
                plot_output = args.plot_output

            plot_obm_series(daily_values, plot_output)

        if not args.quiet:
            defined_count = sum(1 for value in daily_values.values() if value is not None)
            missing_count = len(daily_values) - defined_count

            print(f"Wrote {len(daily_values)} observations to {args.output}", file=sys.stderr)
            print(f"Series ID: {SERIES_ID}", file=sys.stderr)
            print(
                f"Date range: {args.start_date.isoformat()} to {args.end_date.isoformat()}",
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
                f"Counted blocks: {diagnostics['counted_blocks']}",
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
