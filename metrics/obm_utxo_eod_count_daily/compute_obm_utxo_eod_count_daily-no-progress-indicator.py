#!/usr/bin/env python3
"""
compute_obm_utxo_eod_count_daily.py

Compute the Open Bitcoin Metrics end-of-day UTXO count series:

    obm_utxo_eod_count_daily

Definition:

    obm_utxo_eod_count_daily reports the number of spendable unspent
    transaction outputs after processing the highest-height block assigned to
    each UTC calendar day.

Output schema:

    date,series_id,value,unit,frequency,release_version

Important conventions:

    - This is a protocol-state metric, not a flow.
    - Coinbase outputs are included if they are not provably unspendable.
    - Coinbase maturity is not applied as an exclusion. Immature coinbase
      outputs are part of the UTXO set, even though they cannot yet be spent.
    - Provably unspendable outputs are excluded at creation time.
    - Non-coinbase inputs subtract one UTXO each.
    - Dates with no assigned block are written as NaN because there is no
      end-of-day block under the selected UTC block-timestamp convention.

Checkpoint convention:

    The UTXO count is cumulative. If --start_date is 2009-01-03 and no
    checkpoint is provided, the script scans from genesis with initial count 0.

    If --start_date is different from 2009-01-03, the user must provide:

        --start_date_eod_utxo_count

    This value is interpreted as the trusted UTXO count at the end of
    --start_date under the same counting convention used by this script. The
    script writes that value for --start_date and starts block-by-block
    computation from the following chain position.

Requirements:

    - Bitcoin Core full node
    - RPC access

Notes:

    - The metric is computed directly from decoded block data.
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
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


SERIES_ID = "obm_utxo_eod_count_daily"
UNIT = "outputs"
FREQUENCY = "daily"
DEFAULT_RELEASE_VERSION = "OBM v0.1.0"
MISSING_VALUE = "NaN"
CANONICAL_GENESIS_START_DATE = date(2009, 1, 3)


def parse_utc_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date {value!r}. Expected format: YYYY-MM-DD."
        ) from exc


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

    def get_block(self, block_hash: str, verbosity: int = 2) -> Dict[str, Any]:
        return self.call("getblock", [block_hash, verbosity])


def get_block_time(client: BitcoinRpcClient, height: int) -> int:
    block_hash = client.get_block_hash(height)
    block = client.get_block(block_hash, verbosity=1)
    return int(block["time"])


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


def find_checkpoint_height_for_eod_date(
    client: BitcoinRpcClient,
    *,
    checkpoint_date: date,
    tip_height: int,
    height_margin: int,
) -> int:
    """
    Find the highest block height whose UTC block date is not later than the
    checkpoint date.

    This is used when the user provides a trusted end-of-start-day UTXO count.
    The script then starts scanning at checkpoint_height + 1.

    Bitcoin block timestamps are not strictly monotonic with height. Therefore,
    the binary-search anchor is expanded on both sides by height_margin before
    selecting the highest qualifying block.
    """
    checkpoint_end_ts = utc_timestamp(utc_datetime_from_date_end(checkpoint_date))

    approx_height = find_last_height_at_or_before_timestamp(
        client, checkpoint_end_ts, tip_height
    )

    scan_start = max(0, approx_height - height_margin)
    scan_end = min(tip_height, approx_height + height_margin)

    best_height: Optional[int] = None

    for height in range(scan_start, scan_end + 1):
        block_hash = client.get_block_hash(height)
        block = client.get_block(block_hash, verbosity=1)
        block_date = utc_date_from_timestamp(int(block["time"]))

        if block_date <= checkpoint_date:
            if best_height is None or height > best_height:
                best_height = height

    if best_height is None:
        raise RuntimeError(
            f"Could not find any block assigned to {checkpoint_date.isoformat()} "
            "or earlier inside the checkpoint boundary scan. Increase "
            "--height_margin or check the selected start date."
        )

    return best_height


def is_coinbase_tx(tx: Dict[str, Any]) -> bool:
    vin = tx.get("vin", [])
    return bool(vin) and "coinbase" in vin[0]


def is_provably_unspendable_vout(vout: Dict[str, Any]) -> bool:
    script_pub_key = vout.get("scriptPubKey", {})

    if script_pub_key.get("type") == "nulldata":
        return True

    script_hex = script_pub_key.get("hex")
    if isinstance(script_hex, str) and script_hex.lower().startswith("6a"):
        return True

    return False


def count_spent_outputs(tx: Dict[str, Any]) -> int:
    if is_coinbase_tx(tx):
        return 0

    return len(tx.get("vin", []))


def compute_utxo_eod_count(
    client: BitcoinRpcClient,
    *,
    start_date: date,
    end_date: date,
    height_margin: int,
    start_date_eod_utxo_count: Optional[int],
    verbose: bool,
) -> Tuple[Dict[date, Optional[int]], Dict[date, Optional[int]], Dict[str, int]]:
    info = client.get_blockchain_info()
    tip_height = int(info["blocks"])

    if start_date_eod_utxo_count is not None and start_date_eod_utxo_count < 0:
        raise ValueError("--start_date_eod_utxo_count must be non-negative.")

    if start_date != CANONICAL_GENESIS_START_DATE and start_date_eod_utxo_count is None:
        raise ValueError(
            "--start_date_eod_utxo_count is mandatory when --start_date is "
            f"different from {CANONICAL_GENESIS_START_DATE.isoformat()}."
        )

    end_ts = utc_timestamp(utc_datetime_from_date_end(end_date))

    approx_end_height = find_last_height_at_or_before_timestamp(
        client, end_ts, tip_height
    )
    scan_end_height = min(tip_height, approx_end_height + height_margin)

    checkpoint_height = -1
    checkpoint_mode = start_date_eod_utxo_count is not None

    if checkpoint_mode:
        checkpoint_height = find_checkpoint_height_for_eod_date(
            client,
            checkpoint_date=start_date,
            tip_height=tip_height,
            height_margin=height_margin,
        )
        scan_start_height = checkpoint_height + 1
        utxo_count = int(start_date_eod_utxo_count)
    else:
        scan_start_height = 0
        utxo_count = 0

    if scan_start_height > scan_end_height:
        # This can legitimately happen if the requested range only contains the
        # checkpoint date. In that case, we still write the checkpoint value.
        scan_start_height = scan_end_height + 1

    if verbose:
        print(f"Chain tip height: {tip_height}", file=sys.stderr)
        print(f"Checkpoint mode: {checkpoint_mode}", file=sys.stderr)
        print(f"Checkpoint height: {checkpoint_height}", file=sys.stderr)
        print(f"Initial UTXO count: {utxo_count}", file=sys.stderr)
        print(f"Approximate end height: {approx_end_height}", file=sys.stderr)
        if scan_start_height <= scan_end_height:
            print(
                f"Expanded scan interval: {scan_start_height} to {scan_end_height}",
                file=sys.stderr,
            )
        else:
            print("Expanded scan interval: empty", file=sys.stderr)

    daily_eod_count: Dict[date, Optional[int]] = {
        d: None for d in daterange(start_date, end_date)
    }
    daily_last_height: Dict[date, Optional[int]] = {
        d: None for d in daterange(start_date, end_date)
    }

    if checkpoint_mode:
        daily_eod_count[start_date] = utxo_count
        daily_last_height[start_date] = checkpoint_height

    scanned_blocks = 0
    counted_blocks = 0
    created_spendable_outputs = 0
    spent_outputs = 0
    provably_unspendable_outputs = 0

    if scan_start_height <= scan_end_height:
        for height in range(scan_start_height, scan_end_height + 1):
            block_hash = client.get_block_hash(height)
            block = client.get_block(block_hash, verbosity=2)

            scanned_blocks += 1

            block_time = int(block["time"])
            block_date = utc_date_from_timestamp(block_time)

            block_created = 0
            block_spent = 0
            block_unspendable = 0

            for tx in block.get("tx", []):
                for vout in tx.get("vout", []):
                    if is_provably_unspendable_vout(vout):
                        block_unspendable += 1
                    else:
                        block_created += 1

                block_spent += count_spent_outputs(tx)

            utxo_count += block_created
            utxo_count -= block_spent

            if utxo_count < 0:
                raise RuntimeError(
                    f"UTXO count became negative after block {height}: {utxo_count}. "
                    "This indicates an inconsistent initial state or counting rule."
                )

            created_spendable_outputs += block_created
            spent_outputs += block_spent
            provably_unspendable_outputs += block_unspendable

            # In checkpoint mode, blocks dated on or before start_date are not
            # expected after checkpoint_height. If they appear because of a very
            # unusual timestamp pattern outside the boundary margin, they are
            # deliberately not recorded in the output interval.
            if start_date < block_date <= end_date or (
                not checkpoint_mode and start_date <= block_date <= end_date
            ):
                counted_blocks += 1

                previous_height = daily_last_height[block_date]
                if previous_height is None or height > previous_height:
                    daily_last_height[block_date] = height
                    daily_eod_count[block_date] = utxo_count

    diagnostics = {
        "tip_height": tip_height,
        "checkpoint_mode": int(checkpoint_mode),
        "checkpoint_height": checkpoint_height,
        "initial_utxo_count": int(start_date_eod_utxo_count or 0),
        "approx_end_height": approx_end_height,
        "scan_start_height": scan_start_height,
        "scan_end_height": scan_end_height,
        "scanned_blocks": scanned_blocks,
        "counted_blocks": counted_blocks,
        "created_spendable_outputs": created_spendable_outputs,
        "spent_outputs": spent_outputs,
        "provably_unspendable_outputs": provably_unspendable_outputs,
        "final_utxo_count": utxo_count,
    }

    return daily_eod_count, daily_last_height, diagnostics


def write_obm_csv(
    output_path: Path,
    daily_values: Dict[date, Optional[int]],
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
            value_str = MISSING_VALUE if value is None else str(value)

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
    daily_values: Dict[date, Optional[int]],
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
        values.append(value)

    if not dates:
        raise RuntimeError("No defined UTXO count observations are available to plot.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(dates, values)

    start = min(dates).isoformat()
    end = max(dates).isoformat()

    ax.set_title(
        f"Open Bitcoin Metrics: End-of-Day UTXO Count "
        f"({start} to {end})"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("outputs")
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
            "Compute obm_utxo_eod_count_daily by scanning Bitcoin blocks "
            "through Bitcoin Core RPC."
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
        "--start_date_eod_utxo_count",
        type=int,
        default=None,
        help=(
            "Trusted UTXO count at the end of --start_date under the same "
            "counting convention. Mandatory when --start_date is different "
            f"from {CANONICAL_GENESIS_START_DATE.isoformat()}. If supplied, "
            "the script writes this value for --start_date and starts "
            "block-by-block computation from the following chain position."
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
        default=288,
        help=(
            "Extra blocks scanned around the checkpoint boundary and after "
            "the approximate end height. Default: 288."
        ),
    )

    parser.add_argument(
        "--output",
        default="obm_utxo_eod_count_daily.csv",
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

        if args.height_margin < 0:
            raise ValueError("--height_margin must be non-negative.")

        if (
            args.start_date_eod_utxo_count is not None
            and args.start_date_eod_utxo_count < 0
        ):
            raise ValueError("--start_date_eod_utxo_count must be non-negative.")

        if (
            args.start_date != CANONICAL_GENESIS_START_DATE
            and args.start_date_eod_utxo_count is None
        ):
            raise ValueError(
                "--start_date_eod_utxo_count is mandatory when --start_date is "
                f"different from {CANONICAL_GENESIS_START_DATE.isoformat()}."
            )

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

        daily_values, daily_last_heights, diagnostics = compute_utxo_eod_count(
            client,
            start_date=args.start_date,
            end_date=args.end_date,
            height_margin=args.height_margin,
            start_date_eod_utxo_count=args.start_date_eod_utxo_count,
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
            print(f"Checkpoint mode: {bool(diagnostics['checkpoint_mode'])}", file=sys.stderr)
            print(f"Checkpoint height: {diagnostics['checkpoint_height']}", file=sys.stderr)
            print(f"Defined observations: {defined_count}", file=sys.stderr)
            print(f"NaN observations: {missing_count}", file=sys.stderr)
            print(f"Scanned blocks: {diagnostics['scanned_blocks']}", file=sys.stderr)
            print(
                f"Counted blocks in requested dates after checkpoint: "
                f"{diagnostics['counted_blocks']}",
                file=sys.stderr,
            )
            print(
                f"Created spendable outputs scanned: "
                f"{diagnostics['created_spendable_outputs']}",
                file=sys.stderr,
            )
            print(f"Spent outputs scanned: {diagnostics['spent_outputs']}", file=sys.stderr)
            print(
                f"Provably unspendable outputs excluded: "
                f"{diagnostics['provably_unspendable_outputs']}",
                file=sys.stderr,
            )
            print(
                f"Final scanned UTXO count: {diagnostics['final_utxo_count']}",
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
