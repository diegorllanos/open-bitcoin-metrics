#!/usr/bin/env python3
"""
compute_obm_supply_btc_daily.py

Generate the Open Bitcoin Metrics Bitcoin supply series:

    obm_supply_btc_daily

The script reads an existing OBM complete daily issuance CSV file:

    obm_issuance_btc_daily.csv

and computes cumulative issuance between 2009-01-01 and --end_date,
both inclusive.

Output schema:

    date,series_id,value,unit,frequency,release_version

Example:

    python3 compute_obm_supply_btc_daily.py \
        obm_issuance_btc_daily.csv \
        --end_date 2024-01-31 \
        --output obm_supply_btc_daily.csv

The cumulative value is reset at 2009-01-01. Therefore, the value for
start_date equals the daily issuance on 2009-01-01.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Dict, List, Optional


SERIES_ID = "obm_supply_btc_daily"
INPUT_SERIES_ID = "obm_issuance_btc_daily"
UNIT = "BTC"
FREQUENCY = "daily"

# Enough precision for BTC-denominated arithmetic.
getcontext().prec = 28


@dataclass
class DailyIssuanceRow:
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


def read_issuance_csv(input_path: Path) -> Dict[date, DailyIssuanceRow]:
    required_fields = {
        "date",
        "series_id",
        "value",
        "unit",
        "frequency",
        "release_version",
    }

    rows: Dict[date, DailyIssuanceRow] = {}

    with input_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError("Input CSV file has no header row.")

        missing_fields = required_fields.difference(reader.fieldnames)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"Input CSV file is missing required field(s): {missing}")

        for row_number, row in enumerate(reader, start=2):
            row_date = parse_utc_date(row["date"])
            series_id = row["series_id"].strip()
            unit = row["unit"].strip()
            frequency = row["frequency"].strip()

            if series_id != INPUT_SERIES_ID:
                raise ValueError(
                    f"Unexpected series_id at row {row_number}: {series_id}. "
                    f"Expected {INPUT_SERIES_ID}."
                )

            if unit != UNIT:
                raise ValueError(
                    f"Unexpected unit at row {row_number}: {unit}. Expected {UNIT}."
                )

            if frequency != FREQUENCY:
                raise ValueError(
                    f"Unexpected frequency at row {row_number}: {frequency}. "
                    f"Expected {FREQUENCY}."
                )

            if row_date in rows:
                raise ValueError(f"Duplicate date found in input CSV: {row_date}")

            try:
                value = Decimal(row["value"])
            except Exception as exc:
                raise ValueError(
                    f"Invalid numeric value at row {row_number}: {row['value']}"
                ) from exc

            rows[row_date] = DailyIssuanceRow(
                date=row_date,
                value=value,
                release_version=row["release_version"].strip(),
            )

    if not rows:
        raise ValueError("Input CSV file contains no data rows.")

    return rows


def compute_accumulated_issuance(
    issuance_rows: Dict[date, DailyIssuanceRow],
    start_date: date,
    end_date: date,
) -> Dict[date, Decimal]:
    if start_date > end_date:
        raise ValueError("--start_date must be earlier than or equal to --end_date.")

    output: Dict[date, Decimal] = {}
    running_total = Decimal("0")

    current = start_date
    while current <= end_date:
        if current not in issuance_rows:
            raise ValueError(f"Missing input observation for date: {current.isoformat()}")

        running_total += issuance_rows[current].value
        output[current] = running_total

        current = date.fromordinal(current.toordinal() + 1)

    return output


def infer_release_version(
    issuance_rows: Dict[date, DailyIssuanceRow],
    start_date: date,
    end_date: date,
) -> str:
    release_versions = set()

    current = start_date
    while current <= end_date:
        if current in issuance_rows:
            release_versions.add(issuance_rows[current].release_version)
        current = date.fromordinal(current.toordinal() + 1)

    if len(release_versions) == 1:
        return next(iter(release_versions))

    if len(release_versions) == 0:
        return "OBM v0.1.0"

    versions = ", ".join(sorted(release_versions))
    raise ValueError(
        "Input interval contains multiple release_version values: "
        f"{versions}. Please regenerate the source file with a single release version."
    )


def write_obm_csv(
    output_path: Path,
    accum_values: Dict[date, Decimal],
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

        for d in sorted(accum_values):
            writer.writerow(
                {
                    "date": d.isoformat(),
                    "series_id": SERIES_ID,
                    "value": f"{accum_values[d]:.8f}",
                    "unit": UNIT,
                    "frequency": FREQUENCY,
                    "release_version": release_version,
                }
            )


def plot_obm_series(
    accum_values: Dict[date, Decimal],
    output_path: Path,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "The --plot flag requires matplotlib. Install it with: "
            "python3 -m pip install matplotlib"
        ) from exc

    dates = sorted(accum_values)
    values = [float(accum_values[d]) for d in dates]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(dates, values)

    start_date = date(2009, 1, 1)
    end_date = max(dates).isoformat()

    ax.set_title(
        f"Open Bitcoin Metrics: Accumulated Bitcoin Issuance "
        f"({start_date} to {end_date})"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Accumulated BTC issued")
    ax.grid(True, alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate accumulated Bitcoin issuance from an existing "
            "obm_issuance_btc_daily CSV file."
        )
    )

    parser.add_argument(
        "input_csv",
        help="Input CSV file for obm_issuance_btc_daily.",
    )

    parser.add_argument(
        "--end_date",
        required=True,
        type=parse_utc_date,
        help="End date, inclusive, in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--output",
        default="obm_supply_btc_daily.csv",
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
        input_path = Path(args.input_csv)
        output_path = Path(args.output)

        issuance_rows = read_issuance_csv(input_path)

        accum_values = compute_accumulated_issuance(
            issuance_rows=issuance_rows,
            end_date=args.end_date,
            start_date=date(2009, 1, 1)
        )

        release_version = infer_release_version(
            issuance_rows=issuance_rows,
            end_date=args.end_date,
            start_date=date(2009, 1, 1)
        )

        write_obm_csv(
            output_path=output_path,
            accum_values=accum_values,
            release_version=release_version,
        )

        print(
            f"Wrote {len(accum_values)} daily observations to {output_path}",
            file=sys.stderr,
        )

        if args.plot:
            if args.plot_output is not None:
                plot_output_path = Path(args.plot_output)
            else:
                plot_output_path = output_path.with_suffix(".png")

            plot_obm_series(
                accum_values=accum_values,
                output_path=plot_output_path,
            )

            print(f"Wrote plot to {plot_output_path}", file=sys.stderr)

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
