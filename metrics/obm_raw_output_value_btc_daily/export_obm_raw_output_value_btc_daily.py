#!/usr/bin/env python3
"""
export_obm_raw_output_value_btc_daily.py

Export obm_raw_output_value_btc_daily from the OBM spent-output indexer
SQLite database.

Definition:
    obm_raw_output_value_btc_daily reports the total BTC value of outputs
    created by non-coinbase transactions in blocks assigned to each UTC day.

Database identity:
    For non-coinbase transactions:
        fee = input value - output value

    Therefore, by UTC date:
        raw_output_value = spent_value - fees

This script does not scan the blockchain. It reads already computed daily
aggregates from the OBM indexer database.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


getcontext().prec = 50

SERIES_ID = "obm_raw_output_value_btc_daily"
UNIT = "BTC"
FREQUENCY = "daily"
DEFAULT_RELEASE_VERSION = "OBM v0.1.0"
SATOSHIS_PER_BTC = Decimal("100000000")

DEFAULT_DAILY_TABLE_CANDIDATES = (
    "daily_aggregates",
    "daily_aggregate",
    "daily_metrics",
    "daily_stats",
    "obm_daily_aggregates",
)

DEFAULT_DATE_COLUMN_CANDIDATES = (
    "date",
    "day",
    "utc_date",
)

DEFAULT_SPENT_VALUE_SATS_COLUMN_CANDIDATES = (
    "spent_value_sats",
    "total_spent_value_sats",
    "spent_output_value_sats",
    "total_spent_output_value_sats",
    "spent_value",
    "total_spent_value",
)

DEFAULT_FEES_SATS_COLUMN_CANDIDATES = (
    "fees_sats",
    "total_fees_sats",
    "tx_fees_sats",
    "transaction_fees_sats",
    "total_transaction_fees_sats",
    "fees",
    "total_fees",
)

DEFAULT_SPENT_VALUE_BTC_COLUMN_CANDIDATES = (
    "spent_value_btc",
    "total_spent_value_btc",
    "spent_output_value_btc",
    "total_spent_output_value_btc",
)

DEFAULT_FEES_BTC_COLUMN_CANDIDATES = (
    "fees_btc",
    "total_fees_btc",
    "tx_fees_btc",
    "transaction_fees_btc",
    "total_transaction_fees_btc",
)


def parse_utc_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date {value!r}. Expected format: YYYY-MM-DD."
        ) from exc


def daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


@dataclass(frozen=True)
class ColumnSelection:
    table: str
    date_column: str
    spent_value_column: str
    fees_column: str
    value_mode: str


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def list_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def list_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({quote_identifier(table_name)})").fetchall()
    return [str(row[1]) for row in rows]


def first_present(candidates: Sequence[str], available: Sequence[str]) -> Optional[str]:
    available_set = set(available)
    for candidate in candidates:
        if candidate in available_set:
            return candidate
    return None


def resolve_table(conn: sqlite3.Connection, requested_table: Optional[str]) -> str:
    if requested_table is not None:
        if not table_exists(conn, requested_table):
            raise ValueError(
                f"Table {requested_table!r} not found. "
                f"Available tables: {', '.join(list_tables(conn))}"
            )
        return requested_table

    for candidate in DEFAULT_DAILY_TABLE_CANDIDATES:
        if table_exists(conn, candidate):
            return candidate

    raise ValueError(
        "Could not auto-detect the daily aggregate table. "
        "Use --table to specify it explicitly. "
        f"Available tables: {', '.join(list_tables(conn))}"
    )


def resolve_columns(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    requested_date_column: Optional[str],
    requested_spent_value_column: Optional[str],
    requested_fees_column: Optional[str],
    value_mode: str,
) -> ColumnSelection:
    columns = list_columns(conn, table_name)

    if not columns:
        raise ValueError(f"Table {table_name!r} has no columns or does not exist.")

    date_column = requested_date_column or first_present(
        DEFAULT_DATE_COLUMN_CANDIDATES,
        columns,
    )

    if date_column is None:
        raise ValueError(
            f"Could not auto-detect the date column in table {table_name!r}. "
            f"Available columns: {', '.join(columns)}"
        )

    if date_column not in columns:
        raise ValueError(
            f"Date column {date_column!r} not found in table {table_name!r}. "
            f"Available columns: {', '.join(columns)}"
        )

    if value_mode == "auto":
        spent_sats = requested_spent_value_column or first_present(
            DEFAULT_SPENT_VALUE_SATS_COLUMN_CANDIDATES,
            columns,
        )
        fees_sats = requested_fees_column or first_present(
            DEFAULT_FEES_SATS_COLUMN_CANDIDATES,
            columns,
        )

        if spent_sats is not None and fees_sats is not None:
            spent_value_column = spent_sats
            fees_column = fees_sats
            resolved_mode = "sats"
        else:
            spent_btc = requested_spent_value_column or first_present(
                DEFAULT_SPENT_VALUE_BTC_COLUMN_CANDIDATES,
                columns,
            )
            fees_btc = requested_fees_column or first_present(
                DEFAULT_FEES_BTC_COLUMN_CANDIDATES,
                columns,
            )

            if spent_btc is None or fees_btc is None:
                raise ValueError(
                    "Could not auto-detect spent-value and fee columns. "
                    "Use --spent_value_column and --fees_column explicitly. "
                    f"Available columns in {table_name!r}: {', '.join(columns)}"
                )

            spent_value_column = spent_btc
            fees_column = fees_btc
            resolved_mode = "btc"

    elif value_mode == "sats":
        spent_value_column = requested_spent_value_column or first_present(
            DEFAULT_SPENT_VALUE_SATS_COLUMN_CANDIDATES,
            columns,
        )
        fees_column = requested_fees_column or first_present(
            DEFAULT_FEES_SATS_COLUMN_CANDIDATES,
            columns,
        )
        resolved_mode = "sats"

    elif value_mode == "btc":
        spent_value_column = requested_spent_value_column or first_present(
            DEFAULT_SPENT_VALUE_BTC_COLUMN_CANDIDATES,
            columns,
        )
        fees_column = requested_fees_column or first_present(
            DEFAULT_FEES_BTC_COLUMN_CANDIDATES,
            columns,
        )
        resolved_mode = "btc"

    else:
        raise ValueError("--value_mode must be one of: auto, sats, btc.")

    if spent_value_column is None or fees_column is None:
        raise ValueError(
            f"Could not auto-detect required {resolved_mode} columns. "
            "Use --spent_value_column and --fees_column explicitly. "
            f"Available columns in {table_name!r}: {', '.join(columns)}"
        )

    for selected in (spent_value_column, fees_column):
        if selected not in columns:
            raise ValueError(
                f"Column {selected!r} not found in table {table_name!r}. "
                f"Available columns: {', '.join(columns)}"
            )

    return ColumnSelection(
        table=table_name,
        date_column=date_column,
        spent_value_column=spent_value_column,
        fees_column=fees_column,
        value_mode=resolved_mode,
    )


def parse_decimal_value(value: object, *, column: str, obs_date: date) -> Decimal:
    if value is None:
        raise ValueError(
            f"Missing value in column {column!r} for date {obs_date.isoformat()}."
        )

    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(
            f"Invalid numeric value in column {column!r} for date "
            f"{obs_date.isoformat()}: {value!r}"
        ) from exc


def parse_int_sats(value: object, *, column: str, obs_date: date) -> int:
    decimal_value = parse_decimal_value(value, column=column, obs_date=obs_date)
    if decimal_value != decimal_value.to_integral_value():
        raise ValueError(
            f"Expected integer satoshi value in column {column!r} for date "
            f"{obs_date.isoformat()}, found {value!r}."
        )
    return int(decimal_value)


def fetch_daily_component_rows(
    conn: sqlite3.Connection,
    *,
    selection: ColumnSelection,
    start_date: date,
    end_date: date,
) -> List[Tuple[str, object, object]]:
    table = quote_identifier(selection.table)
    date_col = quote_identifier(selection.date_column)
    spent_col = quote_identifier(selection.spent_value_column)
    fees_col = quote_identifier(selection.fees_column)

    query = f"""
        SELECT {date_col}, {spent_col}, {fees_col}
        FROM {table}
        WHERE {date_col} >= ?
          AND {date_col} <= ?
        ORDER BY {date_col}
    """

    return conn.execute(query, (start_date.isoformat(), end_date.isoformat())).fetchall()


def compute_raw_output_value_from_db(
    conn: sqlite3.Connection,
    *,
    selection: ColumnSelection,
    start_date: date,
    end_date: date,
    missing_dates_as_zero: bool,
) -> Tuple[Dict[date, Decimal], Dict[str, int]]:
    daily_values: Dict[date, Optional[Decimal]] = {
        d: None for d in daterange(start_date, end_date)
    }

    rows = fetch_daily_component_rows(
        conn,
        selection=selection,
        start_date=start_date,
        end_date=end_date,
    )

    seen_dates = set()
    duplicate_dates = set()

    for raw_date, raw_spent_value, raw_fees in rows:
        obs_date = parse_utc_date(str(raw_date))

        if obs_date in seen_dates:
            duplicate_dates.add(obs_date)
        seen_dates.add(obs_date)

        if selection.value_mode == "sats":
            spent_value_sats = parse_int_sats(
                raw_spent_value,
                column=selection.spent_value_column,
                obs_date=obs_date,
            )
            fees_sats = parse_int_sats(
                raw_fees,
                column=selection.fees_column,
                obs_date=obs_date,
            )
            raw_output_sats = spent_value_sats - fees_sats

            if raw_output_sats < 0:
                raise ValueError(
                    f"Negative raw output value for {obs_date.isoformat()}: "
                    f"{spent_value_sats} - {fees_sats} = {raw_output_sats} sats."
                )

            daily_values[obs_date] = Decimal(raw_output_sats) / SATOSHIS_PER_BTC

        else:
            spent_value_btc = parse_decimal_value(
                raw_spent_value,
                column=selection.spent_value_column,
                obs_date=obs_date,
            )
            fees_btc = parse_decimal_value(
                raw_fees,
                column=selection.fees_column,
                obs_date=obs_date,
            )
            raw_output_btc = spent_value_btc - fees_btc

            if raw_output_btc < 0:
                raise ValueError(
                    f"Negative raw output value for {obs_date.isoformat()}: "
                    f"{spent_value_btc} - {fees_btc} = {raw_output_btc} BTC."
                )

            daily_values[obs_date] = raw_output_btc

    if duplicate_dates:
        duplicates = ", ".join(sorted(d.isoformat() for d in duplicate_dates))
        raise ValueError(f"Duplicate dates found in database result: {duplicates}")

    missing_dates = [d for d, value in daily_values.items() if value is None]

    if missing_dates_as_zero:
        for d in missing_dates:
            daily_values[d] = Decimal("0")
    elif missing_dates:
        preview = ", ".join(d.isoformat() for d in missing_dates[:10])
        suffix = "" if len(missing_dates) <= 10 else f", ... ({len(missing_dates)} missing dates)"
        raise ValueError(
            "Missing aggregate rows for selected dates: "
            f"{preview}{suffix}. Use --missing_dates_as_zero if this is expected."
        )

    final_values: Dict[date, Decimal] = {
        d: value if value is not None else Decimal("0")
        for d, value in daily_values.items()
    }

    diagnostics = {
        "rows_read": len(rows),
        "missing_dates": len(missing_dates),
        "defined_dates": len(final_values) - len(missing_dates),
    }

    return final_values, diagnostics


def write_obm_csv(
    output_path: Path,
    daily_values: Dict[date, Decimal],
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
            writer.writerow(
                {
                    "date": d.isoformat(),
                    "series_id": SERIES_ID,
                    "value": f"{daily_values[d]:.8f}",
                    "unit": UNIT,
                    "frequency": FREQUENCY,
                    "release_version": release_version,
                }
            )


def plot_obm_series(daily_values: Dict[date, Decimal], output_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "The --plot flag requires matplotlib. Install it with: "
            "python3 -m pip install matplotlib"
        ) from exc

    dates = sorted(daily_values)
    values = [float(daily_values[d]) for d in dates]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(dates, values)

    start = min(dates).isoformat()
    end = max(dates).isoformat()

    ax.set_title(
        f"Open Bitcoin Metrics: Daily Raw Output Value "
        f"({start} to {end})"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("BTC")
    ax.grid(True, alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export obm_raw_output_value_btc_daily from the OBM spent-output "
            "indexer SQLite database using raw_output_value = spent_value - fees."
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
        "--state_db",
        # required=True,
        default="cache/obm_spent_output_indexer.sqlite",
        type=Path,
        help=(
            "Path to the persistent SQLite database generated by "
            "obm_spent_output_indexer.py. "
            "Default: cache/obm_spent_output_indexer.sqlite."
        ),

    )

    parser.add_argument(
        "--table",
        default=None,
        help=(
            "Daily aggregate table name. If omitted, the script attempts to "
            "auto-detect a common OBM aggregate table name."
        ),
    )

    parser.add_argument(
        "--date_column",
        default=None,
        help="Date column name. If omitted, the script attempts to auto-detect it.",
    )

    parser.add_argument(
        "--spent_value_column",
        default=None,
        help=(
            "Column containing daily spent output value. Prefer a satoshi "
            "integer column when available."
        ),
    )

    parser.add_argument(
        "--fees_column",
        default=None,
        help=(
            "Column containing daily transaction fees. Prefer a satoshi "
            "integer column when available."
        ),
    )

    parser.add_argument(
        "--value_mode",
        choices=("auto", "sats", "btc"),
        default="auto",
        help=(
            "Interpretation of --spent_value_column and --fees_column. "
            "Use 'sats' for integer satoshis, 'btc' for BTC values, or 'auto' "
            "to prefer satoshi columns and fall back to BTC columns. Default: auto."
        ),
    )

    parser.add_argument(
        "--missing_dates_as_zero",
        action="store_true",
        help=(
            "Write zero for dates missing from the aggregate table. Use this "
            "when missing daily aggregate rows are expected to mean no block or "
            "no activity under the OBM convention."
        ),
    )

    parser.add_argument(
        "--output",
        default="obm_raw_output_value_btc_daily.csv",
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

        if not args.state_db.exists():
            raise FileNotFoundError(f"Database file not found: {args.state_db}")

        conn = sqlite3.connect(str(args.state_db))

        try:
            table = resolve_table(conn, args.table)
            selection = resolve_columns(
                conn,
                table_name=table,
                requested_date_column=args.date_column,
                requested_spent_value_column=args.spent_value_column,
                requested_fees_column=args.fees_column,
                value_mode=args.value_mode,
            )

            daily_values, diagnostics = compute_raw_output_value_from_db(
                conn,
                selection=selection,
                start_date=args.start_date,
                end_date=args.end_date,
                missing_dates_as_zero=args.missing_dates_as_zero,
            )
        finally:
            conn.close()

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
            print(f"Wrote {len(daily_values)} observations to {args.output}", file=sys.stderr)
            print(f"Series ID: {SERIES_ID}", file=sys.stderr)
            print(
                f"Date range: {args.start_date.isoformat()} to {args.end_date.isoformat()}",
                file=sys.stderr,
            )
            print(f"Database: {args.state_db}", file=sys.stderr)
            print(f"Table: {selection.table}", file=sys.stderr)
            print(f"Date column: {selection.date_column}", file=sys.stderr)
            print(f"Spent-value column: {selection.spent_value_column}", file=sys.stderr)
            print(f"Fees column: {selection.fees_column}", file=sys.stderr)
            print(f"Value mode: {selection.value_mode}", file=sys.stderr)
            print(f"Rows read: {diagnostics['rows_read']}", file=sys.stderr)
            print(f"Missing dates: {diagnostics['missing_dates']}", file=sys.stderr)
            if args.plot:
                print(f"Wrote plot to {plot_output}", file=sys.stderr)

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
