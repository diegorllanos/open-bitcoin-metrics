#!/usr/bin/env python3
"""
compute_obm_block_count_daily.py

Generate the Open Bitcoin Metrics daily block-count series:

    obm_block_count_daily

The script queries a local Bitcoin Core node through JSON-RPC, counts the
number of blocks whose timestamps fall within the requested UTC date interval,
and writes a standardized OBM CSV file.

Output schema:

    date,series_id,value,unit,frequency,release_version

Example:

    python3 compute_obm_block_count_daily.py \
        --start_date 2024-01-01 \
        --end_date 2024-01-31 \
        --output data/daily/obm_block_count_daily.csv \
        --release_version "OBM v0.1.0"

Assumptions:
    - Bitcoin Core is running and fully synchronized.
    - The RPC interface is accessible.
    - Dates are interpreted in UTC.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SERIES_ID = "obm_block_count_daily"
UNIT = "blocks"
FREQUENCY = "daily"
DEFAULT_RELEASE_VERSION = "OBM v0.1.0"


# ---------------------------------------------------------------------
# JSON-RPC client
# ---------------------------------------------------------------------

@dataclass
class BitcoinRPCConfig:
    rpc_url: str
    rpc_user: Optional[str]
    rpc_password: Optional[str]


class BitcoinRPC:
    def __init__(self, config: BitcoinRPCConfig) -> None:
        self.config = config
        self._request_id = 0

        if config.rpc_user is not None and config.rpc_password is not None:
            credentials = f"{config.rpc_user}:{config.rpc_password}".encode("utf-8")
            self.auth_header = "Basic " + base64.b64encode(credentials).decode("ascii")
        else:
            self.auth_header = None

    def call(self, method: str, params: Optional[List[Any]] = None) -> Any:
        self._request_id += 1

        payload = {
            "jsonrpc": "1.0",
            "id": self._request_id,
            "method": method,
            "params": params or [],
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        if self.auth_header is not None:
            headers["Authorization"] = self.auth_header

        request = Request(self.config.rpc_url, data=data, headers=headers)

        try:
            with urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"RPC HTTP error {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not connect to Bitcoin Core RPC: {exc}") from exc

        result = json.loads(raw)

        if result.get("error") is not None:
            raise RuntimeError(f"RPC error in {method}: {result['error']}")

        return result["result"]


# ---------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------

def read_cookie_auth(cookie_path: Path) -> tuple[str, str]:
    if not cookie_path.exists():
        raise FileNotFoundError(
            f"Cookie file not found: {cookie_path}. "
            "Either provide --rpc_user and --rpc_password, or check --datadir."
        )

    content = cookie_path.read_text(encoding="utf-8").strip()

    if ":" not in content:
        raise ValueError(f"Invalid cookie file format: {cookie_path}")

    user, password = content.split(":", 1)
    return user, password


def build_rpc_config(args: argparse.Namespace) -> BitcoinRPCConfig:
    rpc_url = f"http://{args.rpc_host}:{args.rpc_port}/"

    rpc_user = args.rpc_user
    rpc_password = args.rpc_password

    if rpc_user is None or rpc_password is None:
        datadir = Path(args.datadir).expanduser()
        cookie_path = (
            Path(args.cookie_path).expanduser()
            if args.cookie_path
            else datadir / ".cookie"
        )
        rpc_user, rpc_password = read_cookie_auth(cookie_path)

    return BitcoinRPCConfig(
        rpc_url=rpc_url,
        rpc_user=rpc_user,
        rpc_password=rpc_password,
    )


# ---------------------------------------------------------------------
# Date and block-height helpers
# ---------------------------------------------------------------------

def parse_utc_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Expected format: YYYY-MM-DD."
        ) from exc


def date_to_utc_start_timestamp(d: date) -> int:
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return int(dt.timestamp())


def date_to_utc_end_timestamp(d: date) -> int:
    dt = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
    return int(dt.timestamp())


def timestamp_to_utc_date(ts: int) -> date:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def daterange(start: date, end: date) -> List[date]:
    days: List[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def get_block_time(rpc: BitcoinRPC, height: int) -> int:
    block_hash = rpc.call("getblockhash", [height])
    block = rpc.call("getblock", [block_hash, 1])
    return int(block["time"])


def find_first_height_at_or_after_timestamp(
    rpc: BitcoinRPC,
    target_ts: int,
    best_height: int,
) -> int:
    """
    Approximate binary search using block timestamps.

    Bitcoin block timestamps are not strictly monotonic, so the result is later
    expanded backward by --height_margin before the actual scan.
    """
    low = 0
    high = best_height

    while low < high:
        mid = (low + high) // 2
        mid_time = get_block_time(rpc, mid)

        if mid_time < target_ts:
            low = mid + 1
        else:
            high = mid

    return low


def find_last_height_at_or_before_timestamp(
    rpc: BitcoinRPC,
    target_ts: int,
    best_height: int,
) -> int:
    """
    Approximate binary search using block timestamps.

    Bitcoin block timestamps are not strictly monotonic, so the result is later
    expanded forward by --height_margin before the actual scan.
    """
    low = 0
    high = best_height

    while low < high:
        mid = (low + high + 1) // 2
        mid_time = get_block_time(rpc, mid)

        if mid_time <= target_ts:
            low = mid
        else:
            high = mid - 1

    return low


# ---------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------

def get_block_timestamp(rpc: BitcoinRPC, height: int) -> int:
    block_hash = rpc.call("getblockhash", [height])
    block = rpc.call("getblock", [block_hash, 1])
    return int(block["time"])


def compute_block_count_daily(
    rpc: BitcoinRPC,
    start_date: date,
    end_date: date,
    height_margin: int,
    progress_every: int,
) -> Dict[date, int]:
    if start_date > end_date:
        raise ValueError("--start_date must be earlier than or equal to --end_date.")

    start_ts = date_to_utc_start_timestamp(start_date)
    end_ts = date_to_utc_end_timestamp(end_date)

    blockchain_info = rpc.call("getblockchaininfo")
    best_height = int(blockchain_info["blocks"])

    tip_time = get_block_time(rpc, best_height)
    if end_ts > tip_time:
    tip_date = timestamp_to_utc_date(tip_time)
    raise ValueError(
        f"The requested end_date is after the current chain tip date "
        f"({tip_date.isoformat()}). The node cannot provide future observations."
    )

    if start_ts > tip_time:
        raise ValueError(
            "The requested start_date is after the current chain tip timestamp. "
            "The node cannot provide future observations."
        )

    approx_start_height = find_first_height_at_or_after_timestamp(
        rpc=rpc,
        target_ts=start_ts,
        best_height=best_height,
    )

    approx_end_height = find_last_height_at_or_before_timestamp(
        rpc=rpc,
        target_ts=end_ts,
        best_height=best_height,
    )

    scan_start_height = max(0, approx_start_height - height_margin)
    scan_end_height = min(best_height, approx_end_height + height_margin)

    counts: Dict[date, int] = {d: 0 for d in daterange(start_date, end_date)}

    total_blocks = scan_end_height - scan_start_height + 1

    print(
        f"Scanning heights {scan_start_height:,} to {scan_end_height:,} "
        f"({total_blocks:,} blocks).",
        file=sys.stderr,
    )

    for i, height in enumerate(range(scan_start_height, scan_end_height + 1), start=1):
        block_time = get_block_timestamp(rpc, height)
        block_date = timestamp_to_utc_date(block_time)

        if start_date <= block_date <= end_date:
            counts[block_date] += 1

        if progress_every > 0 and i % progress_every == 0:
            print(
                f"Processed {i:,}/{total_blocks:,} blocks "
                f"up to height {height:,}.",
                file=sys.stderr,
            )

    return counts


# ---------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------

def write_obm_csv(
    output_path: Path,
    counts: Dict[date, int],
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

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for d in sorted(counts):
            writer.writerow(
                {
                    "date": d.isoformat(),
                    "series_id": SERIES_ID,
                    "value": counts[d],
                    "unit": UNIT,
                    "frequency": FREQUENCY,
                    "release_version": release_version,
                }
            )


# ---------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------

def plot_obm_series(
    counts: Dict[date, int],
    output_path: Path,
) -> None:
    """
    Generate a line plot for the computed daily block-count series.

    Matplotlib is imported only when this function is called, so the basic
    CSV-generation workflow does not require matplotlib.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "The --plot flag requires matplotlib. Install it with: "
            "python3 -m pip install matplotlib"
        ) from exc

    dates = sorted(counts)
    values = [counts[d] for d in dates]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(dates, values)

    start_date = min(dates).isoformat()
    end_date = max(dates).isoformat()

    ax.set_title(
        f"Open Bitcoin Metrics: Daily Block Count "
        f"({start_date} to {end_date})"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Blocks per day")
    ax.grid(True, alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the OBM daily Bitcoin block-count series."
    )

    parser.add_argument(
        "--start_date",
        required=True,
        type=parse_utc_date,
        help="Start date, inclusive, in YYYY-MM-DD format. Interpreted as UTC.",
    )

    parser.add_argument(
        "--end_date",
        required=True,
        type=parse_utc_date,
        help="End date, inclusive, in YYYY-MM-DD format. Interpreted as UTC.",
    )

    parser.add_argument(
        "--output",
        default="obm_block_count_daily.csv",
        help="Output CSV file path.",
    )

    parser.add_argument(
        "--release_version",
        default=DEFAULT_RELEASE_VERSION,
        help=f"Dataset release version. Default: {DEFAULT_RELEASE_VERSION}.",
    )

    parser.add_argument(
        "--rpc_host",
        default="127.0.0.1",
        help="Bitcoin Core RPC host. Default: 127.0.0.1.",
    )

    parser.add_argument(
        "--rpc_port",
        default=8332,
        type=int,
        help="Bitcoin Core RPC port. Default: 8332 for mainnet.",
    )

    parser.add_argument(
        "--rpc_user",
        default=None,
        help="Bitcoin Core RPC username. If omitted, cookie auth is used.",
    )

    parser.add_argument(
        "--rpc_password",
        default=None,
        help="Bitcoin Core RPC password. If omitted, cookie auth is used.",
    )

    parser.add_argument(
        "--datadir",
        default="~/.bitcoin",
        help="Bitcoin Core data directory. Used to locate .cookie if needed.",
    )

    parser.add_argument(
        "--cookie_path",
        default=None,
        help="Explicit path to Bitcoin Core .cookie file.",
    )

    parser.add_argument(
        "--height_margin",
        default=288,
        type=int,
        help=(
            "Extra blocks scanned before and after the approximate date bounds. "
            "This protects against non-monotonic block timestamps. "
            "Default: 288, about two days of blocks."
        ),
    )

    parser.add_argument(
        "--progress_every",
        default=1000,
        type=int,
        help="Print progress every N blocks. Use 0 to disable. Default: 1000.",
    )

    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate a plot of the computed series.",
    )

    parser.add_argument(
        "--plot_output",
        default=None,
        help=(
            "Output path for the plot. If omitted and --plot is used, "
            "the plot is saved next to the CSV file with .png extension."
        ),
    )

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        config = build_rpc_config(args)
        rpc = BitcoinRPC(config)

        counts = compute_block_count_daily(
            rpc=rpc,
            start_date=args.start_date,
            end_date=args.end_date,
            height_margin=args.height_margin,
            progress_every=args.progress_every,
        )

        output_path = Path(args.output)

        write_obm_csv(
            output_path=output_path,
            counts=counts,
            release_version=args.release_version,
        )

        print(f"Wrote {len(counts)} daily observations to {output_path}", file=sys.stderr)

        if args.plot:
            if args.plot_output is not None:
                plot_output_path = Path(args.plot_output)
            else:
                plot_output_path = output_path.with_suffix(".png")

            plot_obm_series(
                counts=counts,
                output_path=plot_output_path,
            )

            print(f"Wrote plot to {plot_output_path}", file=sys.stderr)

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

