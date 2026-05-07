#!/usr/bin/env python3
"""
obm_spent_output_indexer.py

Persistent spent-output indexer for Open Bitcoin Metrics (OBM).

This script scans the Bitcoin blockchain once, maintains a local SQLite
outpoint state, and stores daily aggregate data needed to export several
OBM metrics later.

It is an internal state-builder, not a metric-specific CSV exporter.

The indexer maintains:

    1. A live outpoint table:
        outpoints(txid, vout, value_sats, created_time, created_height)

    2. Daily aggregate tables:
        daily_aggregates
        daily_age_band_aggregates

    3. Processing metadata:
        processed_blocks
        metadata

The resulting database can later be used to export metrics such as:

    obm_cdd_btcxdays_daily
    obm_spent_value_btc_daily
    obm_dormancy_days_daily
    obm_bincdd365d_btc_daily
    obm_lth_spent_value_155d_btc_daily
    obm_sth_spent_value_155d_btc_daily
    obm_lth_cdd_155d_btcxdays_daily
    obm_sth_cdd_155d_btcxdays_daily
    obm_fees_btc_daily
    obm_issuance_btc_daily
    obm_miner_revenue_btc_daily

Definitions used internally:

    spent value:
        value of previous outputs consumed by non-coinbase inputs

    CDD:
        value_sats * age_days, stored as satoshi-days

    age_days:
        max(0, (spent_time - created_time) / 86400)

    fees:
        sum(inputs) - sum(outputs) for non-coinbase transactions

    coinbase output:
        total output value of the coinbase transaction

    issuance:
        coinbase output value minus fees

Note:
    If coinbase outputs are lower than total fees, issuance can be negative.
    This reflects net supply change under the chosen accounting convention.

Important:
    This script handles historical duplicate coinbase transaction IDs by
    overwriting the earlier txid:vout entry in the live outpoint state and
    recording the event in metadata. The overwritten output is not counted as
    spent and therefore does not generate spent value or CDD.

Assumptions:
    - Bitcoin Core is running and fully synchronized.
    - The RPC interface is accessible.
    - Dates are interpreted in UTC.
    - A non-pruned node is strongly recommended.
"""

from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

INDEXER_ID = "obm_spent_output_indexer"
STATE_SCHEMA_VERSION = "1"
DEFINITION_VERSION = "spent_output_indexer_v1"

SATOSHIS_PER_BTC = Decimal("100000000")
SECONDS_PER_DAY = Decimal("86400")

CDD_THRESHOLD_365D_SECONDS = 365 * 24 * 60 * 60
LTH_THRESHOLD_155D_SECONDS = 155 * 24 * 60 * 60

# Precision for fractional satoshi-days.
getcontext().prec = 50


AGE_BANDS: List[Tuple[str, Optional[int], Optional[int]]] = [
    ("0d_1d", 0, 1 * 24 * 60 * 60),
    ("1d_1w", 1 * 24 * 60 * 60, 7 * 24 * 60 * 60),
    ("1w_1m", 7 * 24 * 60 * 60, 30 * 24 * 60 * 60),
    ("1m_3m", 30 * 24 * 60 * 60, 90 * 24 * 60 * 60),
    ("3m_6m", 90 * 24 * 60 * 60, 180 * 24 * 60 * 60),
    ("6m_1y", 180 * 24 * 60 * 60, 365 * 24 * 60 * 60),
    ("1y_2y", 365 * 24 * 60 * 60, 2 * 365 * 24 * 60 * 60),
    ("2y_3y", 2 * 365 * 24 * 60 * 60, 3 * 365 * 24 * 60 * 60),
    ("3y_5y", 3 * 365 * 24 * 60 * 60, 5 * 365 * 24 * 60 * 60),
    ("5y_7y", 5 * 365 * 24 * 60 * 60, 7 * 365 * 24 * 60 * 60),
    ("7y_10y", 7 * 365 * 24 * 60 * 60, 10 * 365 * 24 * 60 * 60),
    ("10y_plus", 10 * 365 * 24 * 60 * 60, None),
]


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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def date_to_utc_start_timestamp(d: date) -> int:
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return int(dt.timestamp())


def date_to_utc_end_timestamp(d: date) -> int:
    dt = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
    return int(dt.timestamp())


def timestamp_to_utc_date(ts: int) -> date:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def get_block_hash(rpc: BitcoinRPC, height: int) -> str:
    return str(rpc.call("getblockhash", [height]))


def get_block_time(rpc: BitcoinRPC, height: int) -> int:
    block_hash = get_block_hash(rpc, height)
    block = rpc.call("getblock", [block_hash, 1])
    return int(block["time"])


def get_decoded_block(
    rpc: BitcoinRPC,
    height: int,
) -> Dict[str, Any]:
    block_hash = get_block_hash(rpc, height)

    # Verbosity 2 gives decoded transactions, including txid, vin, vout,
    # and output values. Previous-output values are reconstructed locally
    # from the persistent outpoint table.
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
# Numeric helpers
# ---------------------------------------------------------------------

def btc_to_sats(value: Any) -> int:
    dec = Decimal(str(value))
    sats = (dec * SATOSHIS_PER_BTC).to_integral_value(rounding=ROUND_DOWN)
    return int(sats)


def decimal_to_text(value: Decimal) -> str:
    return str(value)


def text_to_decimal(value: str) -> Decimal:
    return Decimal(str(value))


def output_age_seconds(created_time: int, spent_time: int) -> Tuple[int, bool]:
    age = spent_time - created_time
    if age < 0:
        return 0, True
    return age, False


def age_seconds_to_days(age_seconds: int) -> Decimal:
    return Decimal(age_seconds) / SECONDS_PER_DAY


def cdd_sats_days(value_sats: int, age_seconds: int) -> Decimal:
    return Decimal(value_sats) * age_seconds_to_days(age_seconds)


def age_band_for_seconds(age_seconds: int) -> str:
    for label, lower, upper in AGE_BANDS:
        lower_ok = lower is None or age_seconds >= lower
        upper_ok = upper is None or age_seconds < upper
        if lower_ok and upper_ok:
            return label

    raise RuntimeError(f"No age band found for age_seconds={age_seconds}")


# ---------------------------------------------------------------------
# SQLite schema and metadata
# ---------------------------------------------------------------------

def connect_state_db(db_path: Path, reset: bool) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if reset and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-262144;")      # 256 MiB cache
    conn.execute("PRAGMA mmap_size=268435456;")     # 256 MiB mmap, if supported
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
        CREATE TABLE IF NOT EXISTS daily_aggregates (
            date TEXT PRIMARY KEY,

            spent_value_sats TEXT NOT NULL DEFAULT '0',
            spent_output_count INTEGER NOT NULL DEFAULT 0,

            cdd_sats_days TEXT NOT NULL DEFAULT '0',
            spent_output_age_days_sum TEXT NOT NULL DEFAULT '0',

            spent_value_365d_sats TEXT NOT NULL DEFAULT '0',
            cdd_365d_sats_days TEXT NOT NULL DEFAULT '0',

            spent_value_155d_sats TEXT NOT NULL DEFAULT '0',
            cdd_155d_sats_days TEXT NOT NULL DEFAULT '0',

            spent_value_lt_155d_sats TEXT NOT NULL DEFAULT '0',
            cdd_lt_155d_sats_days TEXT NOT NULL DEFAULT '0',

            fees_sats TEXT NOT NULL DEFAULT '0',
            coinbase_output_sats TEXT NOT NULL DEFAULT '0',
            issuance_sats TEXT NOT NULL DEFAULT '0',

            negative_age_outputs INTEGER NOT NULL DEFAULT 0
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_age_band_aggregates (
            date TEXT NOT NULL,
            age_band TEXT NOT NULL,
            spent_value_sats TEXT NOT NULL DEFAULT '0',
            cdd_sats_days TEXT NOT NULL DEFAULT '0',
            spent_output_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (date, age_band)
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


def increment_metadata_counter(
    conn: sqlite3.Connection,
    key: str,
    amount: int = 1,
) -> None:
    old_value = get_metadata(conn, key)
    old_int = int(old_value) if old_value is not None else 0
    set_metadata(conn, key, old_int + amount)


def validate_or_initialize_metadata(conn: sqlite3.Connection) -> None:
    schema_version = get_metadata(conn, "state_schema_version")

    if schema_version is None:
        set_metadata(conn, "state_schema_version", STATE_SCHEMA_VERSION)
        set_metadata(conn, "indexer_id", INDEXER_ID)
        set_metadata(conn, "definition_version", DEFINITION_VERSION)
        conn.commit()
        return

    if schema_version != STATE_SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported state DB schema version {schema_version}. "
            f"Expected {STATE_SCHEMA_VERSION}. Use --reset_state_db to rebuild."
        )

    indexer_id = get_metadata(conn, "indexer_id")
    if indexer_id is not None and indexer_id != INDEXER_ID:
        raise RuntimeError(
            f"State DB belongs to {indexer_id}, not {INDEXER_ID}."
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


def verify_chain_consistency(rpc: BitcoinRPC, conn: sqlite3.Connection) -> None:
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
            "This simple-safe indexer does not roll back automatically. "
            "Rebuild the state with --reset_state_db."
        )


# ---------------------------------------------------------------------
# Daily aggregate update helpers
# ---------------------------------------------------------------------

def ensure_daily_aggregate_row(conn: sqlite3.Connection, block_date: date) -> None:
    conn.execute(
        """
        INSERT INTO daily_aggregates (date)
        VALUES (?)
        ON CONFLICT(date) DO NOTHING;
        """,
        (block_date.isoformat(),),
    )


def add_to_daily_aggregates(
    conn: sqlite3.Connection,
    block_date: date,
    spent_value_sats: int,
    spent_output_count: int,
    cdd_value_sats_days: Decimal,
    spent_output_age_days_sum: Decimal,
    spent_value_365d_sats: int,
    cdd_365d_sats_days: Decimal,
    spent_value_155d_sats: int,
    cdd_155d_sats_days: Decimal,
    spent_value_lt_155d_sats: int,
    cdd_lt_155d_sats_days: Decimal,
    fees_sats: int,
    coinbase_output_sats: int,
    issuance_sats: int,
    negative_age_outputs: int,
) -> None:
    ensure_daily_aggregate_row(conn, block_date)
    date_str = block_date.isoformat()

    row = conn.execute(
        """
        SELECT
            spent_value_sats,
            spent_output_count,
            cdd_sats_days,
            spent_output_age_days_sum,
            spent_value_365d_sats,
            cdd_365d_sats_days,
            spent_value_155d_sats,
            cdd_155d_sats_days,
            spent_value_lt_155d_sats,
            cdd_lt_155d_sats_days,
            fees_sats,
            coinbase_output_sats,
            issuance_sats,
            negative_age_outputs
        FROM daily_aggregates
        WHERE date = ?;
        """,
        (date_str,),
    ).fetchone()

    if row is None:
        raise RuntimeError(f"Could not read daily aggregate row for {date_str}.")

    new_values = {
        "spent_value_sats": int(row[0]) + spent_value_sats,
        "spent_output_count": int(row[1]) + spent_output_count,
        "cdd_sats_days": text_to_decimal(row[2]) + cdd_value_sats_days,
        "spent_output_age_days_sum": text_to_decimal(row[3]) + spent_output_age_days_sum,
        "spent_value_365d_sats": int(row[4]) + spent_value_365d_sats,
        "cdd_365d_sats_days": text_to_decimal(row[5]) + cdd_365d_sats_days,
        "spent_value_155d_sats": int(row[6]) + spent_value_155d_sats,
        "cdd_155d_sats_days": text_to_decimal(row[7]) + cdd_155d_sats_days,
        "spent_value_lt_155d_sats": int(row[8]) + spent_value_lt_155d_sats,
        "cdd_lt_155d_sats_days": text_to_decimal(row[9]) + cdd_lt_155d_sats_days,
        "fees_sats": int(row[10]) + fees_sats,
        "coinbase_output_sats": int(row[11]) + coinbase_output_sats,
        "issuance_sats": int(row[12]) + issuance_sats,
        "negative_age_outputs": int(row[13]) + negative_age_outputs,
    }

    conn.execute(
        """
        UPDATE daily_aggregates
        SET
            spent_value_sats = ?,
            spent_output_count = ?,
            cdd_sats_days = ?,
            spent_output_age_days_sum = ?,
            spent_value_365d_sats = ?,
            cdd_365d_sats_days = ?,
            spent_value_155d_sats = ?,
            cdd_155d_sats_days = ?,
            spent_value_lt_155d_sats = ?,
            cdd_lt_155d_sats_days = ?,
            fees_sats = ?,
            coinbase_output_sats = ?,
            issuance_sats = ?,
            negative_age_outputs = ?
        WHERE date = ?;
        """,
        (
            str(new_values["spent_value_sats"]),
            new_values["spent_output_count"],
            decimal_to_text(new_values["cdd_sats_days"]),
            decimal_to_text(new_values["spent_output_age_days_sum"]),
            str(new_values["spent_value_365d_sats"]),
            decimal_to_text(new_values["cdd_365d_sats_days"]),
            str(new_values["spent_value_155d_sats"]),
            decimal_to_text(new_values["cdd_155d_sats_days"]),
            str(new_values["spent_value_lt_155d_sats"]),
            decimal_to_text(new_values["cdd_lt_155d_sats_days"]),
            str(new_values["fees_sats"]),
            str(new_values["coinbase_output_sats"]),
            str(new_values["issuance_sats"]),
            new_values["negative_age_outputs"],
            date_str,
        ),
    )


def add_to_daily_age_band(
    conn: sqlite3.Connection,
    block_date: date,
    age_band: str,
    spent_value_sats: int,
    cdd_value_sats_days: Decimal,
    spent_output_count: int,
) -> None:
    date_str = block_date.isoformat()

    conn.execute(
        """
        INSERT INTO daily_age_band_aggregates
        (date, age_band, spent_value_sats, cdd_sats_days, spent_output_count)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(date, age_band) DO UPDATE SET
            spent_value_sats =
                CAST(daily_age_band_aggregates.spent_value_sats AS INTEGER)
                + CAST(excluded.spent_value_sats AS INTEGER),
            cdd_sats_days =
                CAST(daily_age_band_aggregates.cdd_sats_days AS TEXT),
            spent_output_count =
                daily_age_band_aggregates.spent_output_count
                + excluded.spent_output_count;
        """,
        (
            date_str,
            age_band,
            str(spent_value_sats),
            decimal_to_text(cdd_value_sats_days),
            spent_output_count,
        ),
    )

    # SQLite cannot safely add arbitrary Decimal text values inside SQL.
    # Therefore, update cdd_sats_days in Python.
    row = conn.execute(
        """
        SELECT cdd_sats_days
        FROM daily_age_band_aggregates
        WHERE date = ? AND age_band = ?;
        """,
        (date_str, age_band),
    ).fetchone()

    if row is None:
        raise RuntimeError(
            f"Could not read daily_age_band_aggregates for "
            f"{date_str}, {age_band}."
        )

    # The INSERT above set cdd_sats_days to the incoming value when new,
    # but left it unchanged when there was a conflict. Detect the conflict
    # path by subtracting only for an existing row is awkward with SQLite.
    # Simpler and clearer approach: read all old values before writing.
    # This function is replaced below by add_age_band_accumulator() during
    # block processing, so this function is not used.
    raise RuntimeError("add_to_daily_age_band() should not be called directly.")


def flush_age_band_accumulators(
    conn: sqlite3.Connection,
    block_date: date,
    accumulators: Dict[str, Dict[str, Any]],
) -> None:
    date_str = block_date.isoformat()

    for age_band, values in accumulators.items():
        spent_value_sats = int(values["spent_value_sats"])
        cdd_value_sats_days = Decimal(values["cdd_sats_days"])
        spent_output_count = int(values["spent_output_count"])

        existing = conn.execute(
            """
            SELECT spent_value_sats, cdd_sats_days, spent_output_count
            FROM daily_age_band_aggregates
            WHERE date = ? AND age_band = ?;
            """,
            (date_str, age_band),
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO daily_age_band_aggregates
                (date, age_band, spent_value_sats, cdd_sats_days, spent_output_count)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    date_str,
                    age_band,
                    str(spent_value_sats),
                    decimal_to_text(cdd_value_sats_days),
                    spent_output_count,
                ),
            )
        else:
            new_spent_value = int(existing[0]) + spent_value_sats
            new_cdd = text_to_decimal(existing[1]) + cdd_value_sats_days
            new_count = int(existing[2]) + spent_output_count

            conn.execute(
                """
                UPDATE daily_age_band_aggregates
                SET spent_value_sats = ?,
                    cdd_sats_days = ?,
                    spent_output_count = ?
                WHERE date = ? AND age_band = ?;
                """,
                (
                    str(new_spent_value),
                    decimal_to_text(new_cdd),
                    new_count,
                    date_str,
                    age_band,
                ),
            )


# ---------------------------------------------------------------------
# Outpoint operations
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

        try:
            conn.execute(
                """
                INSERT INTO outpoints
                (txid, vout, value_sats, created_time, created_height)
                VALUES (?, ?, ?, ?, ?);
                """,
                (txid, n, value_sats, block_time, height),
            )

        except sqlite3.IntegrityError:
            existing = conn.execute(
                """
                SELECT value_sats, created_time, created_height
                FROM outpoints
                WHERE txid = ? AND vout = ?;
                """,
                (txid, n),
            ).fetchone()

            if existing is None:
                raise RuntimeError(
                    "IntegrityError while inserting an outpoint, but the "
                    "conflicting outpoint could not be retrieved. "
                    f"height={height}, block_hash={block_hash}, "
                    f"tx_index={tx_index}, txid={txid}, vout={n}"
                )

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
            # For this local indexer state, the later txid:vout overwrites
            # the earlier live entry. The overwritten output is not counted
            # as spent and therefore does not generate spent value or CDD.
            conn.execute(
                """
                UPDATE outpoints
                SET value_sats = ?,
                    created_time = ?,
                    created_height = ?
                WHERE txid = ? AND vout = ?;
                """,
                (value_sats, block_time, height, txid, n),
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

    # Use SELECT plus DELETE for broader SQLite compatibility.
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


def sum_vout_sats(tx: Dict[str, Any]) -> int:
    total = 0

    for vout in tx.get("vout", []):
        total += btc_to_sats(vout["value"])

    return total


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

    if not isinstance(txs, list) or not txs:
        raise RuntimeError(f"Block {height} contains no transactions.")

    coinbase_tx = txs[0]
    coinbase_output_sats = sum_vout_sats(coinbase_tx)

    spent_value_sats = 0
    spent_output_count = 0
    cdd_total = Decimal("0")
    spent_output_age_days_sum = Decimal("0")

    spent_value_365d_sats = 0
    cdd_365d_total = Decimal("0")

    spent_value_155d_sats = 0
    cdd_155d_total = Decimal("0")

    spent_value_lt_155d_sats = 0
    cdd_lt_155d_total = Decimal("0")

    fees_sats = 0
    negative_age_outputs = 0

    age_band_accumulators: Dict[str, Dict[str, Any]] = {}

    # Insert coinbase outputs first. Later transactions in the same block
    # cannot spend the coinbase because coinbase maturity is required.
    # Inserting now is still safe and keeps processing order simple.
    insert_outputs(
        conn=conn,
        tx=coinbase_tx,
        block_time=block_time,
        height=height,
        block_hash=block_hash,
        tx_index=0,
    )

    for tx_index, tx in enumerate(txs[1:], start=1):
        input_total_sats = 0
        output_total_sats = sum_vout_sats(tx)

        for vin in tx.get("vin", []):
            if "coinbase" in vin:
                raise RuntimeError(
                    f"Unexpected coinbase input in non-coinbase transaction "
                    f"{tx.get('txid', '<unknown>')} at height {height}."
                )

            value_sats, created_time = spend_input(conn, vin)
            input_total_sats += value_sats

            age_seconds, negative_age = output_age_seconds(
                created_time=created_time,
                spent_time=block_time,
            )

            if negative_age:
                negative_age_outputs += 1

            age_days = age_seconds_to_days(age_seconds)
            cdd_value = cdd_sats_days(value_sats, age_seconds)

            spent_value_sats += value_sats
            spent_output_count += 1
            cdd_total += cdd_value
            spent_output_age_days_sum += age_days

            if age_seconds >= CDD_THRESHOLD_365D_SECONDS:
                spent_value_365d_sats += value_sats
                cdd_365d_total += cdd_value

            if age_seconds >= LTH_THRESHOLD_155D_SECONDS:
                spent_value_155d_sats += value_sats
                cdd_155d_total += cdd_value
            else:
                spent_value_lt_155d_sats += value_sats
                cdd_lt_155d_total += cdd_value

            age_band = age_band_for_seconds(age_seconds)
            if age_band not in age_band_accumulators:
                age_band_accumulators[age_band] = {
                    "spent_value_sats": 0,
                    "cdd_sats_days": Decimal("0"),
                    "spent_output_count": 0,
                }

            age_band_accumulators[age_band]["spent_value_sats"] += value_sats
            age_band_accumulators[age_band]["cdd_sats_days"] += cdd_value
            age_band_accumulators[age_band]["spent_output_count"] += 1

        tx_fee_sats = input_total_sats - output_total_sats

        if tx_fee_sats < 0:
            raise RuntimeError(
                f"Negative transaction fee at height {height}, "
                f"txid={tx.get('txid', '<unknown>')}: "
                f"inputs={input_total_sats}, outputs={output_total_sats}."
            )

        fees_sats += tx_fee_sats

        # Insert outputs after spending inputs. This supports valid
        # within-block dependencies where a later transaction spends an
        # output created by an earlier transaction in the same block.
        insert_outputs(
            conn=conn,
            tx=tx,
            block_time=block_time,
            height=height,
            block_hash=block_hash,
            tx_index=tx_index,
        )

    issuance_sats = coinbase_output_sats - fees_sats

    add_to_daily_aggregates(
        conn=conn,
        block_date=block_date,
        spent_value_sats=spent_value_sats,
        spent_output_count=spent_output_count,
        cdd_value_sats_days=cdd_total,
        spent_output_age_days_sum=spent_output_age_days_sum,
        spent_value_365d_sats=spent_value_365d_sats,
        cdd_365d_sats_days=cdd_365d_total,
        spent_value_155d_sats=spent_value_155d_sats,
        cdd_155d_sats_days=cdd_155d_total,
        spent_value_lt_155d_sats=spent_value_lt_155d_sats,
        cdd_lt_155d_sats_days=cdd_lt_155d_total,
        fees_sats=fees_sats,
        coinbase_output_sats=coinbase_output_sats,
        issuance_sats=issuance_sats,
        negative_age_outputs=negative_age_outputs,
    )

    flush_age_band_accumulators(
        conn=conn,
        block_date=block_date,
        accumulators=age_band_accumulators,
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

    max_processed_date = get_metadata(conn, "max_processed_date")
    if max_processed_date is None or block_date > parse_utc_date(max_processed_date):
        set_metadata(conn, "max_processed_date", block_date.isoformat())

    if negative_age_outputs > 0:
        increment_metadata_counter(
            conn,
            "negative_age_outputs_floored",
            negative_age_outputs,
        )


# ---------------------------------------------------------------------
# Target-height selection and processing loop
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

    return min(safe_tip_height, approx_end_height + height_margin)


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
        block = get_decoded_block(rpc, height)
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
# Diagnostics
# ---------------------------------------------------------------------

def print_state_summary(conn: sqlite3.Connection) -> None:
    metadata_rows = conn.execute(
        "SELECT key, value FROM metadata ORDER BY key;"
    ).fetchall()

    print("State metadata:", file=sys.stderr)
    for key, value in metadata_rows:
        print(f"  {key}: {value}", file=sys.stderr)

    outpoint_count = conn.execute(
        "SELECT COUNT(*) FROM outpoints;"
    ).fetchone()[0]

    daily_count = conn.execute(
        "SELECT COUNT(*) FROM daily_aggregates;"
    ).fetchone()[0]

    band_count = conn.execute(
        "SELECT COUNT(*) FROM daily_age_band_aggregates;"
    ).fetchone()[0]

    print(f"Outpoints currently stored: {outpoint_count:,}", file=sys.stderr)
    print(f"Daily aggregate rows: {daily_count:,}", file=sys.stderr)
    print(f"Daily age-band rows: {band_count:,}", file=sys.stderr)


# ---------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the persistent OBM spent-output indexer database. "
            "This scans the blockchain, maintains live outpoints, and stores "
            "daily aggregate tables for CDD, spent value, fees, issuance, "
            "miner revenue, threshold metrics, and age-band metrics."
        )
    )

    parser.add_argument(
        "--start_date",
        required=False,
        type=parse_utc_date,
        default=None,
        help=(
            "Optional start date in YYYY-MM-DD format. This indexer always "
            "processes from genesis or from the last processed block, so this "
            "argument is used only for sanity checks and logging."
        ),
    )

    parser.add_argument(
        "--end_date",
        required=True,
        type=parse_utc_date,
        help="End date, inclusive, in YYYY-MM-DD format. Interpreted as UTC.",
    )

    parser.add_argument(
        "--state_db",
        default="cache/obm_spent_output_indexer.sqlite",
        help=(
            "Path to the persistent SQLite indexer database. "
            "Default: cache/obm_spent_output_indexer.sqlite."
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
        "--release_version",
        default="OBM v0.1.0",
        help=(
            "Dataset release version stored in metadata for later exporters. "
            "Default: OBM v0.1.0."
        ),
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
        help="Print progress every N blocks. Use 0 to disable. Default: 1000.",
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

    return parser


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        if args.start_date is not None and args.start_date > args.end_date:
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
            set_metadata(conn, "release_version", args.release_version)
            conn.commit()

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

            print_state_summary(conn)

        finally:
            conn.close()

        print(
            f"Indexer database updated successfully: {state_db_path}",
            file=sys.stderr,
        )

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
