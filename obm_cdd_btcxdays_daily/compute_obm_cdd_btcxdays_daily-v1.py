#!/usr/bin/env python3
"""
compute_obm_cdd_btcxdays_daily.py

Generate the Open Bitcoin Metrics daily Coin Days Destroyed series:

    obm_cdd_btcxdays_daily

This version is persistent and incremental. It maintains a local SQLite
state database containing:

    1. the current outpoint set;
    2. daily CDD values already computed;
    3. processed block metadata;
    4. processing metadata.

The first run scans from genesis up to the requested target range. Later runs
resume from the last processed block and process only new blocks.

Output CSV schema:

    date,series_id,value,unit,frequency,release_version

Example:

    python3 compute_obm_cdd_btcxdays_daily.py \
        --start_date 2024-01-01 \
        --end_date 2024-01-31 \
        --output data/daily/obm_cdd_btcxdays_daily.csv \
        --state_db cache/obm_cdd_btcxdays_state.sqlite

Definition:

    For each spent output i:

        CDD_i = value_i_BTC * age_i_days

    For each UTC day d:

        CDD_d = sum_i CDD_i

    where i ranges over all outputs spent in blocks assigned to day d.

Important:
    This script uses block timestamps to compute both output age and daily
    assignment. Because Bitcoin block timestamps are not strictly monotonic,
    negative apparent ages can occur in rare boundary cases. The script floors
    negative ages at zero and counts such events for diagnostics.

Assumptions:
    - Bitcoin Core is running and fully synchronized.
    - The node has access to all historical blocks needed by the requested run.
    - Dates are interpreted in UTC.
    - The SQLite state database is treated as part of the reproducible state
      of this metric.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------
# OBM constants
# ---------------------------------------------------------------------

SERIES_ID = "obm_cdd_btcxdays_daily"
UNIT = "BTC-days"
FREQUENCY = "daily"
DEFAULT_RELEASE_VERSION = "OBM v0.1.0"
DEFINITION_VERSION = "cdd_btcxdays_v1"
STATE_SCHEMA_VERSION = "1"

SATOSHIS_PER_BTC = Decimal("100000000")
SECONDS_PER_DAY = Decimal("86400")

# Enough precision for satoshi-day arithmetic.
getcontext().prec = 50


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
            with urlopen(request, timeout=300) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"RPC HTTP error {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not connect to Bitcoin Core RPC: {exc}") from exc

        result = json.loads(raw, parse_float=Decimal)

        if result.get("error") is not None:
            raise RuntimeError(f"RPC error in {method}: {result['error']}")

        return result["result"]


# ---------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------

def read_cookie_auth(cookie_path: Path) -> Tuple[str, str]:
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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def daterange(start: date, end: date) -> List[date]:
    days: List[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def get_block_hash(rpc: BitcoinRPC, height: int) -> str:
    return str(rpc.call("getblockhash", [height]))


def get_block_time(rpc: BitcoinRPC, height: int) -> int:
    block_hash = get_block_hash(rpc, height)
    block = rpc.call("getblock", [block_hash, 1])
    return int(block["time"])


def get_decoded_block_with_transactions(
    rpc: BitcoinRPC,
    height: int,
) -> Dict[str, Any]:
    block_hash = get_block_hash(rpc, height)

    # Verbosity 2 gives decoded transactions, including txid, vin, vout,
    # and output values. We reconstruct previous outputs locally, so
    # verbosity 3 is not required for CDD.
    block = rpc.call("getblock", [block_hash, 2])
    block["hash"] = block_hash
    return block


def find_last_height_at_or_before_timestamp(
    rpc: BitcoinRPC,
    target_ts: int,
    max_height: int,
) -> int:
    """
    Approximate binary search using block timestamps.

    Bitcoin block timestamps are not strictly monotonic. The result is later
    expanded forward by --height_margin before processing.
    """
    low = 0
    high = max_height

    while low < high:
        mid = (low + high + 1) // 2
        mid_time = get_block_time(rpc, mid)

        if mid_time <= target_ts:
            low = mid
        else:
            high = mid - 1

    return low


# ---------------------------------------------------------------------
# BTC and CDD helpers
# ---------------------------------------------------------------------

def btc_to_sats(value: Any) -> int:
    """
    Convert a BTC-denominated value returned by Bitcoin Core into integer
    satoshis.

    Bitcoin Core JSON numbers are parsed as Decimal to avoid binary
    floating-point artifacts.
    """
    dec = Decimal(str(value))
    sats = (dec * SATOSHIS_PER_BTC).to_integral_value(rounding=ROUND_DOWN)
    return int(sats)


def sats_days_to_btc_days_string(sats_days: Decimal) -> str:
    btc_days = sats_days / SATOSHIS_PER_BTC
    return f"{btc_days:.8f}"


def cdd_contribution_sats_days(
    value_sats: int,
    created_time: int,
    spent_time: int,
) -> Tuple[Decimal, bool]:
    """
    Return CDD contribution in satoshi-days.

    age_days = max(0, spent_time - created_time) / 86400

    contribution = value_sats * age_days

    Returns:
        (contribution_sats_days, negative_age_was_floored)
    """
    age_seconds = spent_time - created_time

    if age_seconds < 0:
        age_seconds = 0
        negative_age_was_floored = True
    else:
        negative_age_was_floored = False

    contribution = Decimal(value_sats) * (Decimal(age_seconds) / SECONDS_PER_DAY)
    return contribution, negative_age_was_floored


# ---------------------------------------------------------------------
# SQLite state database
# ---------------------------------------------------------------------

def connect_state_db(db_path: Path, reset: bool) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if reset and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA foreign_keys=ON;")

    initialize_schema(conn)
    validate_or_initialize_metadata(conn)

    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS outpoints (
            txid TEXT NOT NULL,
            vout INTEGER NOT NULL,
            value_sats INTEGER NOT NULL,
            created_time INTEGER NOT NULL,
            created_height INTEGER NOT NULL,
            PRIMARY KEY (txid, vout)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_cdd (
            date TEXT PRIMARY KEY,
            sats_days TEXT NOT NULL
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_blocks (
            height INTEGER PRIMARY KEY,
            hash TEXT NOT NULL,
            block_time INTEGER NOT NULL,
            block_date TEXT NOT NULL
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )

    conn.commit()


def get_metadata(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM metadata WHERE key = ?;",
        (key,),
    ).fetchone()

    if row is None:
        return None

    return str(row[0])


def set_metadata(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        """
        INSERT INTO metadata (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value;
        """,
        (key, str(value)),
    )


def validate_or_initialize_metadata(conn: sqlite3.Connection) -> None:
    schema_version = get_metadata(conn, "state_schema_version")

    if schema_version is None:
        set_metadata(conn, "state_schema_version", STATE_SCHEMA_VERSION)
        set_metadata(conn, "series_id", SERIES_ID)
        set_metadata(conn, "definition_version", DEFINITION_VERSION)
        conn.commit()
        return

    if schema_version != STATE_SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported state DB schema version {schema_version}. "
            f"Expected {STATE_SCHEMA_VERSION}. Use --reset_state_db to rebuild."
        )

    series_id = get_metadata(conn, "series_id")
    if series_id is not None and series_id != SERIES_ID:
        raise RuntimeError(
            f"State DB belongs to series {series_id}, not {SERIES_ID}."
        )

    definition_version = get_metadata(conn, "definition_version")
    if definition_version is not None and definition_version != DEFINITION_VERSION:
        raise RuntimeError(
            f"State DB definition version is {definition_version}, "
            f"but this script expects {DEFINITION_VERSION}. "
            "Use --reset_state_db to rebuild."
        )


def get_last_processed_height(conn: sqlite3.Connection) -> Optional[int]:
    value = get_metadata(conn, "last_processed_height")
    if value is None:
        return None
    return int(value)


def get_last_processed_hash(conn: sqlite3.Connection) -> Optional[str]:
    return get_metadata(conn, "last_processed_hash")


def get_max_processed_date(conn: sqlite3.Connection) -> Optional[date]:
    value = get_metadata(conn, "max_processed_date")
    if value is None:
        return None
    return parse_utc_date(value)


def increment_metadata_counter(
    conn: sqlite3.Connection,
    key: str,
    amount: int = 1,
) -> None:
    old_value = get_metadata(conn, key)
    old_int = int(old_value) if old_value is not None else 0
    set_metadata(conn, key, old_int + amount)


def verify_chain_consistency(rpc: BitcoinRPC, conn: sqlite3.Connection) -> None:
    """
    Simple and safe reorg handling.

    If the last processed block hash no longer matches Bitcoin Core at the same
    height, abort. The user can then rebuild with --reset_state_db.

    This intentionally does not attempt automatic rollback.
    """
    last_height = get_last_processed_height(conn)

    if last_height is None:
        return

    last_hash = get_last_processed_hash(conn)

    if last_hash is None:
        raise RuntimeError(
            "State DB has last_processed_height but no last_processed_hash. "
            "Use --reset_state_db to rebuild."
        )

    current_hash = get_block_hash(rpc, last_height)

    if current_hash != last_hash:
        raise RuntimeError(
            "Possible chain reorganization or inconsistent state DB detected. "
            f"State DB has height {last_height} with hash {last_hash}, "
            f"but Bitcoin Core reports {current_hash}. "
            "This simple-safe script does not roll back automatically. "
            "Rebuild the state with --reset_state_db."
        )


# ---------------------------------------------------------------------
# Outpoint database operations
# ---------------------------------------------------------------------
def insert_outputs(
    conn: sqlite3.Connection,
    tx: Dict[str, Any],
    block_time: int,
    height: int,
    block_hash: str,
    tx_index: int,
) -> None:
    txid = tx["txid"]

    for vout in tx.get("vout", []):
        n = int(vout["n"])
        value_sats = btc_to_sats(vout["value"])

        existing = conn.execute(
            """
            SELECT value_sats, created_time, created_height
            FROM outpoints
            WHERE txid = ? AND vout = ?;
            """,
            (txid, n),
        ).fetchone()

        if existing is not None:
            old_value_sats = int(existing[0])
            old_created_time = int(existing[1])
            old_created_height = int(existing[2])
            old_created_date = timestamp_to_utc_date(old_created_time).isoformat()

            print(
                "WARNING: duplicate outpoint overwritten: "
                f"txid={txid}, vout={n}, "
                f"old_height={old_created_height}, "
                f"old_date={old_created_date}, "
                f"old_time={old_created_time}, "
                f"old_value_sats={old_value_sats}, "
                f"new_height={height}, "
                f"new_time={block_time}, "
                f"new_value_sats={value_sats}, "
                f"block_hash={block_hash}, "
                f"tx_index={tx_index}",
                file=sys.stderr,
            )

            increment_metadata_counter(
                conn,
                "duplicate_outpoints_overwritten",
                1,
            )

        # Historical duplicate txids existed before BIP30 enforcement.
        # In particular, duplicate coinbase transactions at heights 91842
        # and 91880 duplicate earlier coinbases at heights 91812 and 91722.
        # For the local CDD state, the later outpoint overwrites the earlier
        # txid:vout entry. The overwritten output is not counted as spent
        # and therefore does not generate CDD.
        conn.execute(
            """
            INSERT INTO outpoints
            (txid, vout, value_sats, created_time, created_height)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(txid, vout) DO UPDATE SET
                value_sats = excluded.value_sats,
                created_time = excluded.created_time,
                created_height = excluded.created_height;
            """,
            (txid, n, value_sats, block_time, height),
        )

def spend_input(
    conn: sqlite3.Connection,
    vin: Dict[str, Any],
) -> Tuple[int, int]:
    """
    Spend an input and return (value_sats, created_time).

    Coinbase inputs should not be passed to this function.
    """
    prev_txid = vin["txid"]
    prev_vout = int(vin["vout"])

    row = conn.execute(
        """
        SELECT value_sats, created_time
        FROM outpoints
        WHERE txid = ? AND vout = ?;
        """,
        (prev_txid, prev_vout),
    ).fetchone()

    if row is None:
        raise RuntimeError(
            f"Previous output not found in local outpoint database: "
            f"{prev_txid}:{prev_vout}. "
            "This usually means the state DB is incomplete or inconsistent. "
            "Use --reset_state_db to rebuild from genesis."
        )

    conn.execute(
        """
        DELETE FROM outpoints
        WHERE txid = ? AND vout = ?;
        """,
        (prev_txid, prev_vout),
    )

    value_sats = int(row[0])
    created_time = int(row[1])

    return value_sats, created_time


# ---------------------------------------------------------------------
# Daily CDD storage
# ---------------------------------------------------------------------

def add_daily_cdd(
    conn: sqlite3.Connection,
    block_date: date,
    contribution_sats_days: Decimal,
) -> None:
    if contribution_sats_days == 0:
        ensure_daily_cdd_row(conn, block_date)
        return

    date_str = block_date.isoformat()

    row = conn.execute(
        "SELECT sats_days FROM daily_cdd WHERE date = ?;",
        (date_str,),
    ).fetchone()

    if row is None:
        new_value = contribution_sats_days
    else:
        new_value = Decimal(str(row[0])) + contribution_sats_days

    conn.execute(
        """
        INSERT INTO daily_cdd (date, sats_days)
        VALUES (?, ?)
        ON CONFLICT(date) DO UPDATE SET sats_days = excluded.sats_days;
        """,
        (date_str, str(new_value)),
    )


def ensure_daily_cdd_row(conn: sqlite3.Connection, d: date) -> None:
    conn.execute(
        """
        INSERT INTO daily_cdd (date, sats_days)
        VALUES (?, ?)
        ON CONFLICT(date) DO NOTHING;
        """,
        (d.isoformat(), "0"),
    )


def read_daily_cdd_range(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
) -> Dict[date, Decimal]:
    result: Dict[date, Decimal] = {}

    for d in daterange(start_date, end_date):
        row = conn.execute(
            "SELECT sats_days FROM daily_cdd WHERE date = ?;",
            (d.isoformat(),),
        ).fetchone()

        if row is None:
            result[d] = Decimal("0")
        else:
            result[d] = Decimal(str(row[0]))

    return result


# ---------------------------------------------------------------------
# Block processing
# ---------------------------------------------------------------------

def process_block(
    conn: sqlite3.Connection,
    block: Dict[str, Any],
    height: int,
) -> None:
    block_hash = str(block["hash"])
    block_time = int(block["time"])
    block_date = timestamp_to_utc_date(block_time)
    txs = block.get("tx", [])

    if not txs:
        raise RuntimeError(f"Block {height} contains no transactions.")

    block_cdd_sats_days = Decimal("0")
    negative_age_count = 0

    for tx_index, tx in enumerate(txs):
        is_coinbase = tx_index == 0

        if not is_coinbase:
            for vin in tx.get("vin", []):
                if "coinbase" in vin:
                    raise RuntimeError(
                        f"Unexpected coinbase input in non-coinbase transaction "
                        f"{tx.get('txid', '<unknown>')} at height {height}."
                    )

                value_sats, created_time = spend_input(conn, vin)

                contribution, negative_age_was_floored = cdd_contribution_sats_days(
                    value_sats=value_sats,
                    created_time=created_time,
                    spent_time=block_time,
                )

                block_cdd_sats_days += contribution

                if negative_age_was_floored:
                    negative_age_count += 1

        # Insert outputs after spending inputs of this transaction. This order
        # supports valid within-block dependencies where a later transaction
        # spends an output created by an earlier transaction in the same block.
        insert_outputs(
            conn=conn,
            tx=tx,
            block_time=block_time,
            height=height,
            block_hash=block_hash,
            tx_index=tx_index,
        )

    add_daily_cdd(
        conn=conn,
        block_date=block_date,
        contribution_sats_days=block_cdd_sats_days,
    )

    if negative_age_count > 0:
        increment_metadata_counter(
            conn,
            "negative_age_outputs_floored",
            negative_age_count,
        )

    conn.execute(
        """
        INSERT INTO processed_blocks (height, hash, block_time, block_date)
        VALUES (?, ?, ?, ?);
        """,
        (height, block_hash, block_time, block_date.isoformat()),
    )

    set_metadata(conn, "last_processed_height", height)
    set_metadata(conn, "last_processed_hash", block_hash)
    set_metadata(conn, "last_processed_time", block_time)
    set_metadata(conn, "last_processed_date", block_date.isoformat())
    set_metadata(conn, "last_run_utc", utc_now_iso())

    previous_max_date = get_max_processed_date(conn)
    if previous_max_date is None or block_date > previous_max_date:
        set_metadata(conn, "max_processed_date", block_date.isoformat())


def process_missing_blocks(
    rpc: BitcoinRPC,
    conn: sqlite3.Connection,
    target_height: int,
    progress_every: int,
    commit_every: int,
) -> None:
    last_height = get_last_processed_height(conn)
    start_height = 0 if last_height is None else last_height + 1

    if start_height > target_height:
        print(
            f"State DB already processed through height {last_height:,}. "
            f"No new blocks needed for target height {target_height:,}.",
            file=sys.stderr,
        )
        return

    total_blocks = target_height - start_height + 1

    print(
        f"Processing missing blocks from height {start_height:,} "
        f"to {target_height:,} ({total_blocks:,} blocks).",
        file=sys.stderr,
    )

    for i, height in enumerate(range(start_height, target_height + 1), start=1):
        block = get_decoded_block_with_transactions(rpc, height)
        process_block(conn, block, height)

        if commit_every > 0 and i % commit_every == 0:
            conn.commit()

        if progress_every > 0 and i % progress_every == 0:
            print(
                f"Processed {i:,}/{total_blocks:,} new blocks "
                f"up to height {height:,}.",
                file=sys.stderr,
            )

    conn.commit()


# ---------------------------------------------------------------------
# Target-height selection
# ---------------------------------------------------------------------

def determine_target_height(
    rpc: BitcoinRPC,
    end_date: date,
    height_margin: int,
    min_confirmations: int,
) -> int:
    if min_confirmations < 0:
        raise ValueError("--min_confirmations must be non-negative.")

    end_ts = date_to_utc_end_timestamp(end_date)

    blockchain_info = rpc.call("getblockchaininfo")
    best_height = int(blockchain_info["blocks"])

    safe_tip_height = best_height - min_confirmations
    if safe_tip_height < 0:
        raise RuntimeError(
            f"Best height is {best_height}, but --min_confirmations is "
            f"{min_confirmations}. No safe block height is available."
        )

    safe_tip_time = get_block_time(rpc, safe_tip_height)

    if end_ts > safe_tip_time:
        safe_tip_date = timestamp_to_utc_date(safe_tip_time)
        raise ValueError(
            f"The requested end_date {end_date.isoformat()} is not yet safe "
            f"under --min_confirmations={min_confirmations}. "
            f"Safe tip height is {safe_tip_height:,}, whose timestamp date is "
            f"{safe_tip_date.isoformat()}. Use an earlier --end_date, reduce "
            f"--min_confirmations, or run again later."
        )

    approx_end_height = find_last_height_at_or_before_timestamp(
        rpc=rpc,
        target_ts=end_ts,
        max_height=safe_tip_height,
    )

    target_height = min(
        safe_tip_height,
        approx_end_height + height_margin,
    )

    return target_height


# ---------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------

def write_obm_csv(
    output_path: Path,
    cdd_by_date: Dict[date, Decimal],
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

        for d in sorted(cdd_by_date):
            writer.writerow(
                {
                    "date": d.isoformat(),
                    "series_id": SERIES_ID,
                    "value": sats_days_to_btc_days_string(cdd_by_date[d]),
                    "unit": UNIT,
                    "frequency": FREQUENCY,
                    "release_version": release_version,
                }
            )


# ---------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------

def plot_obm_series(
    cdd_by_date: Dict[date, Decimal],
    output_path: Path,
) -> None:
    """
    Generate a line plot for the computed daily CDD series.

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

    dates = sorted(cdd_by_date)
    values = [
        float(cdd_by_date[d] / SATOSHIS_PER_BTC)
        for d in dates
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(dates, values)

    start_date = min(dates).isoformat()
    end_date = max(dates).isoformat()

    ax.set_title(
        f"Open Bitcoin Metrics: Coin Days Destroyed "
        f"({start_date} to {end_date})"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("BTC-days")
    ax.grid(True, alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------
# Export guard
# ---------------------------------------------------------------------

def ensure_export_range_available(
    conn: sqlite3.Connection,
    end_date: date,
) -> None:
    max_processed_date = get_max_processed_date(conn)

    if max_processed_date is None:
        raise RuntimeError(
            "No processed dates are available in the state DB. "
            "The script did not process any blocks."
        )

    if end_date > max_processed_date:
        raise RuntimeError(
            f"The requested end_date {end_date.isoformat()} is beyond the "
            f"maximum processed block date {max_processed_date.isoformat()}. "
            "This should not normally happen after target processing. "
            "Use an earlier end_date or rebuild/update the state DB."
        )


# ---------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the OBM daily Coin Days Destroyed series "
            "using a persistent incremental SQLite state database."
        )
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
        default="obm_cdd_btcxdays_daily.csv",
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
            "Extra blocks scanned after the approximate end-date height. "
            "This protects against non-monotonic block timestamps. "
            "Default: 288, about two days of blocks."
        ),
    )

    parser.add_argument(
        "--min_confirmations",
        default=100,
        type=int,
        help=(
            "Do not process blocks closer than this many confirmations to the "
            "chain tip. This makes reorgs very unlikely for daily data. "
            "Default: 100."
        ),
    )

    parser.add_argument(
        "--progress_every",
        default=1000,
        type=int,
        help="Print progress every N processed blocks. Use 0 to disable. Default: 1000.",
    )

    parser.add_argument(
        "--commit_every",
        default=1000,
        type=int,
        help=(
            "Commit SQLite changes every N processed blocks. "
            "Use 0 to commit only at the end. Default: 1000."
        ),
    )

    parser.add_argument(
        "--state_db",
        default="cache/obm_cdd_btcxdays_state.sqlite",
        help=(
            "Path to the persistent SQLite state database. "
            "Default: cache/obm_cdd_btcxdays_state.sqlite."
        ),
    )

    parser.add_argument(
        "--reset_state_db",
        action="store_true",
        help=(
            "Delete and rebuild the persistent state database from genesis. "
            "Use this after a detected reorg, definition change, or corrupted state."
        ),
    )

    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate a plot of the exported series.",
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


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        if args.start_date > args.end_date:
            raise ValueError("--start_date must be earlier than or equal to --end_date.")

        if args.height_margin < 0:
            raise ValueError("--height_margin must be non-negative.")

        if args.commit_every < 0:
            raise ValueError("--commit_every must be non-negative.")

        config = build_rpc_config(args)
        rpc = BitcoinRPC(config)

        state_db_path = Path(args.state_db)

        conn = connect_state_db(
            db_path=state_db_path,
            reset=args.reset_state_db,
        )

        try:
            verify_chain_consistency(rpc, conn)

            target_height = determine_target_height(
                rpc=rpc,
                end_date=args.end_date,
                height_margin=args.height_margin,
                min_confirmations=args.min_confirmations,
            )

            print(
                f"Target processing height: {target_height:,}",
                file=sys.stderr,
            )

            process_missing_blocks(
                rpc=rpc,
                conn=conn,
                target_height=target_height,
                progress_every=args.progress_every,
                commit_every=args.commit_every,
            )

            ensure_export_range_available(
                conn=conn,
                end_date=args.end_date,
            )

            cdd_by_date = read_daily_cdd_range(
                conn=conn,
                start_date=args.start_date,
                end_date=args.end_date,
            )

        finally:
            conn.close()

        output_path = Path(args.output)

        write_obm_csv(
            output_path=output_path,
            cdd_by_date=cdd_by_date,
            release_version=args.release_version,
        )

        print(
            f"Wrote {len(cdd_by_date)} daily observations to {output_path}",
            file=sys.stderr,
        )

        if args.plot:
            if args.plot_output is not None:
                plot_output_path = Path(args.plot_output)
            else:
                plot_output_path = output_path.with_suffix(".png")

            plot_obm_series(
                cdd_by_date=cdd_by_date,
                output_path=plot_output_path,
            )

            print(f"Wrote plot to {plot_output_path}", file=sys.stderr)

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
