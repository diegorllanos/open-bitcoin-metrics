#!/usr/bin/env python3
"""
plot_obm_csv.py

Plot an Open Bitcoin Metrics CSV time series.

Expected CSV schema:

    date,series_id,value,unit,frequency,release_version

The script plots the 'value' column against 'date'. The title includes:
    - series_id, if available
    - unit
    - frequency
    - start date
    - end date

Example usage:

    python3 plot_obm_csv.py obm_tx_count_daily.csv

    python3 plot_obm_csv.py obm_tx_count_daily.csv --output tx_count.png
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import List


DEFAULT_OUTPUT = "plot.png"


@dataclass
class OBMSeries:
    dates: List[date]
    values: List[float]
    series_id: str
    unit: str
    frequency: str


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid date '{value}'. Expected YYYY-MM-DD.") from exc


def read_obm_csv(input_path: Path) -> OBMSeries:
    required_fields = {
        "date",
        "value",
        "unit",
        "frequency",
    }

    dates: List[date] = []
    values: List[float] = []
    units = set()
    frequencies = set()
    series_ids = set()

    try:
        with input_path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames is None:
                raise ValueError("CSV file has no header row.")

            missing_fields = required_fields.difference(reader.fieldnames)
            if missing_fields:
                missing = ", ".join(sorted(missing_fields))
                raise ValueError(f"CSV file is missing required field(s): {missing}")

            for row_number, row in enumerate(reader, start=2):
                try:
                    d = parse_date(row["date"])
                    v = float(row["value"])
                except Exception as exc:
                    raise ValueError(
                        f"Could not parse row {row_number}: {row}"
                    ) from exc

                dates.append(d)
                values.append(v)

                units.add(row.get("unit", "").strip())
                frequencies.add(row.get("frequency", "").strip())

                if "series_id" in row:
                    sid = row.get("series_id", "").strip()
                    if sid:
                        series_ids.add(sid)

    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Input file not found: {input_path}") from exc

    if not dates:
        raise ValueError("CSV file contains no data rows.")

    if len(units) != 1:
        raise ValueError(
            f"Expected a single unit in the CSV file, found: {sorted(units)}"
        )

    if len(frequencies) != 1:
        raise ValueError(
            f"Expected a single frequency in the CSV file, found: {sorted(frequencies)}"
        )

    if len(series_ids) > 1:
        raise ValueError(
            f"Expected at most one series_id in the CSV file, found: {sorted(series_ids)}"
        )

    # Sort observations by date to avoid plotting problems if the CSV is unordered.
    combined = sorted(zip(dates, values), key=lambda item: item[0])
    sorted_dates = [item[0] for item in combined]
    sorted_values = [item[1] for item in combined]

    series_id = next(iter(series_ids)) if series_ids else "OBM time series"
    unit = next(iter(units))
    frequency = next(iter(frequencies))

    return OBMSeries(
        dates=sorted_dates,
        values=sorted_values,
        series_id=series_id,
        unit=unit,
        frequency=frequency,
    )


def plot_obm_series(series: OBMSeries, output_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "This script requires matplotlib. Install it with:\n"
            "    python3 -m pip install matplotlib"
        ) from exc

    start_date = min(series.dates).isoformat()
    end_date = max(series.dates).isoformat()

    title = (
        f"{series.series_id}\n"
        f"Unit: {series.unit}; Frequency: {series.frequency}; "
        f"Period: {start_date} to {end_date}"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(series.dates, series.values)

    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel(series.unit)
    ax.grid(True, alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot an Open Bitcoin Metrics CSV time series."
    )

    parser.add_argument(
        "input_csv",
        help="Input CSV file following the OBM time-series schema.",
    )

    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output image file. Default: {DEFAULT_OUTPUT}.",
    )

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_path = Path(args.output)

    try:
        series = read_obm_csv(input_path)
        plot_obm_series(series, output_path)
        print(f"Wrote plot to {output_path}", file=sys.stderr)
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
