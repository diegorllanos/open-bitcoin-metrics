#!/usr/bin/env python3
"""
compute_obm_fee_share_miner_revenue_ratio_daily.py

Generate the Open Bitcoin Metrics daily fee-share-of-miner-revenue series:

    obm_fee_share_miner_revenue_ratio_daily

The script reads two existing OBM CSV files:

    obm_issuance_btc_daily.csv
    obm_fees_btc_daily.csv

and computes:

    fee_share = fees / (issuance + fees)

The output is a dimensionless ratio, not a percentage.

Output schema:

    date,series_id,value,unit,frequency,release_version

Example:

    python3 compute_obm_fee_share_miner_revenue_ratio_daily.py \
        data/daily/obm_issuance_btc_daily.csv \
        data/daily/obm_fees_btc_daily.csv \
        --start_date 2024-01-01 \
        --end_date 2024-01-31 \
        --output data/daily/obm_fee_share_miner_revenue_ratio_daily.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Dict, List, Optional, Union


SERIES_ID = "obm_fee_share_miner_revenue_ratio_daily"
ISSUANCE_SERIES_ID = "obm_issuance_btc_daily"
FEES_SERIES_ID = "obm_fees_btc_daily"

UNIT = "ratio"
INPUT_UNIT = "BTC"
FREQUENCY = "daily"
DEFAULT_RELEASE_VERSION = "OBM v0.1.0"

getcontext().prec = 40
FeeShareValue = Optional[Decimal]

@dataclass
class ObmRow:
    date: date
    value: Decimal
    release_version: str


def parse_utc_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Expected format: YYYY-MM-DD."
        ) from exc


def daterange(start: date, end: date) -> List[date]:
    days: List[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def read_obm_csv(
    input_path: Path,
    expected_series_id: str,
    expected_unit: str,
    expected_frequency: str,
) -> Dict[date, ObmRow]:
    required_fields = {
        "date",
        "series_id",
        "value",
        "unit",
        "frequency",
        "release_version",
    }

    rows: Dict[date, ObmRow] = {}

    with input_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError(f"Input CSV file has no header row: {input_path}")

        missing_fields = required_fields.difference(reader.fieldnames)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(
                f"Input CSV file {input_path} is missing required field(s): {missing}"
            )

        for row_number, row in enumerate(reader, start=2):
            row_date = parse_utc_date(row["date"])
            series_id = row["series_id"].strip()
            unit = row["unit"].strip()
            frequency = row["frequency"].strip()

            if series_id != expected_series_id:
                raise ValueError(
                    f"Unexpected series_id in {input_path} at row {row_number}: "
                    f"{series_id}. Expected {expected_series_id}."
                )

            if unit != expected_unit:
                raise ValueError(
                    f"Unexpected unit in {input_path} at row {row_number}: "
                    f"{unit}. Expected {expected_unit}."
                )

            if frequency != expected_frequency:
                raise ValueError(
                    f"Unexpected frequency in {input_path} at row {row_number}: "
                    f"{frequency}. Expected {expected_frequency}."
                )

            if row_date in rows:
                raise ValueError(
                    f"Duplicate date found in {input_path}: {row_date.isoformat()}"
                )

            try:
                value = Decimal(row["value"])
            except Exception as exc:
                raise ValueError(
                    f"Invalid numeric value in {input_path} at row {row_number}: "
                    f"{row['value']}"
                ) from exc

            rows[row_date] = ObmRow(
                date=row_date,
                value=value,
                release_version=row["release_version"].strip(),
            )

    if not rows:
        raise ValueError(f"Input CSV file contains no data rows: {input_path}")

    return rows


def infer_date_interval(
    issuance_rows: Dict[date, ObmRow],
    fees_rows: Dict[date, ObmRow],
    start_date: Optional[date],
    end_date: Optional[date],
) -> tuple[date, date]:
    common_start = max(min(issuance_rows), min(fees_rows))
    common_end = min(max(issuance_rows), max(fees_rows))

    if common_start > common_end:
        raise ValueError("The two input files have no overlapping date interval.")

    effective_start = start_date if start_date is not None else common_start
    effective_end = end_date if end_date is not None else common_end

    if effective_start > effective_end:
        raise ValueError("--start_date must be earlier than or equal to --end_date.")

    if effective_start < common_start or effective_end > common_end:
        raise ValueError(
            "Requested date interval is not fully covered by the overlap of the "
            "two input files. "
            f"Common available interval is {common_start.isoformat()} to "
            f"{common_end.isoformat()}."
        )

    return effective_start, effective_end


def validate_complete_coverage(
    rows: Dict[date, ObmRow],
    start_date: date,
    end_date: date,
    label: str,
) -> None:
    missing_dates = [
        d.isoformat()
        for d in daterange(start_date, end_date)
        if d not in rows
    ]

    if missing_dates:
        preview = ", ".join(missing_dates[:10])
        suffix = "" if len(missing_dates) <= 10 else f", ... ({len(missing_dates)} missing)"
        raise ValueError(
            f"{label} input file is missing required date(s): {preview}{suffix}"
        )


def infer_release_version(
    issuance_rows: Dict[date, ObmRow],
    fees_rows: Dict[date, ObmRow],
    start_date: date,
    end_date: date,
) -> str:
    release_versions = set()

    for d in daterange(start_date, end_date):
        release_versions.add(issuance_rows[d].release_version)
        release_versions.add(fees_rows[d].release_version)

    if len(release_versions) == 1:
        return next(iter(release_versions))

    versions = ", ".join(sorted(release_versions))
    raise ValueError(
        "Input interval contains multiple release_version values across the "
        f"source files: {versions}. Please regenerate the source files with a "
        "single release version."
    )

def compute_fee_share(
    issuance_rows: Dict[date, ObmRow],
    fees_rows: Dict[date, ObmRow],
    start_date: date,
    end_date: date,
) -> Dict[date, FeeShareValue]:
    output: Dict[date, FeeShareValue] = {}

    for d in daterange(start_date, end_date):
        issuance = issuance_rows[d].value
        fees = fees_rows[d].value

        if issuance < 0:
            raise ValueError(f"Negative issuance value found for {d.isoformat()}.")

        if fees < 0:
            raise ValueError(f"Negative fees value found for {d.isoformat()}.")

        denominator = issuance + fees

        if denominator == 0:
            output[d] = None
        else:
            output[d] = fees / denominator

    return output

def write_obm_csv(
    output_path: Path,
    fee_share_by_date: Dict[date, FeeShareValue],
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

        for d in sorted(fee_share_by_date):
            value = fee_share_by_date[d]
            writer.writerow(
                {
                    "date": d.isoformat(),
                    "series_id": SERIES_ID,
                    "value": "" if value is None else f"{value:.12f}",
                    "unit": UNIT,
                    "frequency": FREQUENCY,
                    "release_version": release_version,
                }
            )

def plot_obm_series(
    fee_share_by_date: Dict[date, FeeShareValue],
    output_path: Path,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "The --plot flag requires matplotlib. Install it with: "
            "python3 -m pip install matplotlib"
        ) from exc

    dates = [
        d for d in sorted(fee_share_by_date)
        if fee_share_by_date[d] is not None
    ]
    values = [float(fee_share_by_date[d]) for d in dates]

    if not dates:
        raise ValueError("No defined fee-share values are available to plot.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(dates, values)

    start = min(fee_share_by_date).isoformat()
    end = max(fee_share_by_date).isoformat()

    ax.set_title(
        f"Open Bitcoin Metrics: Fees as Share of Miner Revenue "
        f"({start} to {end})"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Ratio")
    ax.grid(True, alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the OBM daily fee-share-of-miner-revenue ratio from "
            "obm_issuance_btc_daily and obm_fees_btc_daily CSV files."
        )
    )

    parser.add_argument(
        "issuance_csv",
        help="Input CSV file for obm_issuance_btc_daily.",
    )

    parser.add_argument(
        "fees_csv",
        help="Input CSV file for obm_fees_btc_daily.",
    )

    parser.add_argument(
        "--start_date",
        default=None,
        type=parse_utc_date,
        help=(
            "Start date, inclusive, in YYYY-MM-DD format. "
            "If omitted, the first common date in the input files is used."
        ),
    )

    parser.add_argument(
        "--end_date",
        default=None,
        type=parse_utc_date,
        help=(
            "End date, inclusive, in YYYY-MM-DD format. "
            "If omitted, the last common date in the input files is used."
        ),
    )

    parser.add_argument(
        "--output",
        default="obm_fee_share_miner_revenue_ratio_daily.csv",
        help="Output CSV file path.",
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
        issuance_rows = read_obm_csv(
            input_path=Path(args.issuance_csv),
            expected_series_id=ISSUANCE_SERIES_ID,
            expected_unit=INPUT_UNIT,
            expected_frequency=FREQUENCY,
        )

        fees_rows = read_obm_csv(
            input_path=Path(args.fees_csv),
            expected_series_id=FEES_SERIES_ID,
            expected_unit=INPUT_UNIT,
            expected_frequency=FREQUENCY,
        )

        start_date, end_date = infer_date_interval(
            issuance_rows=issuance_rows,
            fees_rows=fees_rows,
            start_date=args.start_date,
            end_date=args.end_date,
        )

        validate_complete_coverage(
            rows=issuance_rows,
            start_date=start_date,
            end_date=end_date,
            label=ISSUANCE_SERIES_ID,
        )

        validate_complete_coverage(
            rows=fees_rows,
            start_date=start_date,
            end_date=end_date,
            label=FEES_SERIES_ID,
        )

        release_version = infer_release_version(
            issuance_rows=issuance_rows,
            fees_rows=fees_rows,
            start_date=start_date,
            end_date=end_date,
        )

        fee_share_by_date = compute_fee_share(
            issuance_rows=issuance_rows,
            fees_rows=fees_rows,
            start_date=start_date,
            end_date=end_date,
        )

        output_path = Path(args.output)

        write_obm_csv(
            output_path=output_path,
            fee_share_by_date=fee_share_by_date,
            release_version=release_version,
        )

        print(
            f"Wrote {len(fee_share_by_date)} daily observations to {output_path}",
            file=sys.stderr,
        )

        if args.plot:
            if args.plot_output is not None:
                plot_output_path = Path(args.plot_output)
            else:
                plot_output_path = output_path.with_suffix(".png")

            plot_obm_series(
                fee_share_by_date=fee_share_by_date,
                output_path=plot_output_path,
            )

            print(f"Wrote plot to {plot_output_path}", file=sys.stderr)

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
