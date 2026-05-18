#!/usr/bin/env python3
"""
plot_obm_cdd_age_band_btcxdays_daily.py

Generate a stacked area plot from the OBM wide daily CDD age-band CSV:

    obm_cdd_age_band_btcxdays_daily

Input CSV schema:

    date,
    series_id,
    cdd_0d_1d_btcxdays,
    cdd_1d_1w_btcxdays,
    cdd_1w_1m_btcxdays,
    cdd_1m_3m_btcxdays,
    cdd_3m_6m_btcxdays,
    cdd_6m_1y_btcxdays,
    cdd_1y_2y_btcxdays,
    cdd_2y_3y_btcxdays,
    cdd_3y_5y_btcxdays,
    cdd_5y_7y_btcxdays,
    cdd_7y_10y_btcxdays,
    cdd_10y_plus_btcxdays,
    unit,
    frequency,
    release_version

The script does not compute or export any metric. It only reads the CSV file
and generates a stacked area chart in which the filled areas represent the
contribution of each age band to total daily Bitcoin Days Destroyed.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


EXPECTED_SERIES_ID = "obm_cdd_age_band_btcxdays_daily"
EXPECTED_UNIT = "BTC-days"
EXPECTED_FREQUENCY = "daily"

AGE_BANDS = [
    "0d_1d",
    "1d_1w",
    "1w_1m",
    "1m_3m",
    "3m_6m",
    "6m_1y",
    "1y_2y",
    "2y_3y",
    "3y_5y",
    "5y_7y",
    "7y_10y",
    "10y_plus",
]

AGE_BAND_COLUMNS = {
    "0d_1d": "cdd_0d_1d_btcxdays",
    "1d_1w": "cdd_1d_1w_btcxdays",
    "1w_1m": "cdd_1w_1m_btcxdays",
    "1m_3m": "cdd_1m_3m_btcxdays",
    "3m_6m": "cdd_3m_6m_btcxdays",
    "6m_1y": "cdd_6m_1y_btcxdays",
    "1y_2y": "cdd_1y_2y_btcxdays",
    "2y_3y": "cdd_2y_3y_btcxdays",
    "3y_5y": "cdd_3y_5y_btcxdays",
    "5y_7y": "cdd_5y_7y_btcxdays",
    "7y_10y": "cdd_7y_10y_btcxdays",
    "10y_plus": "cdd_10y_plus_btcxdays",
}

AGE_BAND_DISPLAY_LABELS = {
    "0d_1d": "0d to 1d",
    "1d_1w": "1d to 1w",
    "1w_1m": "1w to 1m",
    "1m_3m": "1m to 3m",
    "3m_6m": "3m to 6m",
    "6m_1y": "6m to 1y",
    "1y_2y": "1y to 2y",
    "2y_3y": "2y to 3y",
    "3y_5y": "3y to 5y",
    "5y_7y": "5y to 7y",
    "7y_10y": "7y to 10y",
    "10y_plus": "10y+",
}

REQUIRED_COLUMNS = (
    ["date", "series_id"]
    + [AGE_BAND_COLUMNS[band] for band in AGE_BANDS]
    + ["unit", "frequency", "release_version"]
)


def parse_utc_date(raw: str, *, row_number: int) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(
            f"row {row_number}: invalid date {raw!r}. Expected YYYY-MM-DD."
        ) from exc


def parse_decimal(raw: str, *, column: str, row_number: int) -> Decimal:
    if raw is None or raw.strip() == "":
        raise ValueError(
            f"row {row_number}: missing value in column {column!r}."
        )

    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(
            f"row {row_number}: invalid decimal value {raw!r} "
            f"in column {column!r}."
        ) from exc

    if value < 0:
        raise ValueError(
            f"row {row_number}: negative value {value} in column {column!r}."
        )

    return value


def read_cdd_age_band_csv(
    path: Path,
) -> Tuple[List[date], Dict[str, List[Decimal]], str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Input CSV file does not exist: {path}")

    dates: List[date] = []
    values_by_band: Dict[str, List[Decimal]] = {
        band: [] for band in AGE_BANDS
    }
    seen_dates = set()
    release_versions = set()

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames is None:
            raise ValueError(f"{path}: empty CSV file.")

        missing_columns = [
            column for column in REQUIRED_COLUMNS
            if column not in reader.fieldnames
        ]
        if missing_columns:
            raise ValueError(
                f"{path}: missing required columns: "
                + ", ".join(missing_columns)
            )

        for row_number, row in enumerate(reader, start=2):
            obs_date = parse_utc_date(row["date"], row_number=row_number)

            if obs_date in seen_dates:
                raise ValueError(f"row {row_number}: duplicate date {obs_date}.")
            seen_dates.add(obs_date)

            if row["series_id"] != EXPECTED_SERIES_ID:
                raise ValueError(
                    f"row {row_number}: expected series_id "
                    f"{EXPECTED_SERIES_ID!r}, found {row['series_id']!r}."
                )

            if row["unit"] != EXPECTED_UNIT:
                raise ValueError(
                    f"row {row_number}: expected unit {EXPECTED_UNIT!r}, "
                    f"found {row['unit']!r}."
                )

            if row["frequency"] != EXPECTED_FREQUENCY:
                raise ValueError(
                    f"row {row_number}: expected frequency "
                    f"{EXPECTED_FREQUENCY!r}, found {row['frequency']!r}."
                )

            dates.append(obs_date)
            release_versions.add(row["release_version"])

            for band in AGE_BANDS:
                column = AGE_BAND_COLUMNS[band]
                values_by_band[band].append(
                    parse_decimal(
                        row[column],
                        column=column,
                        row_number=row_number,
                    )
                )

    if not dates:
        raise ValueError(f"{path}: no observations found.")

    order = sorted(range(len(dates)), key=lambda i: dates[i])
    sorted_dates = [dates[i] for i in order]
    sorted_values_by_band = {
        band: [values_by_band[band][i] for i in order]
        for band in AGE_BANDS
    }

    start = sorted_dates[0].isoformat()
    end = sorted_dates[-1].isoformat()

    if len(release_versions) == 1:
        release_version = next(iter(release_versions))
    else:
        release_version = "mixed releases"

    return sorted_dates, sorted_values_by_band, release_version, f"{start} to {end}"


def plot_stacked_area(
    dates: Sequence[date],
    values_by_band: Dict[str, Sequence[Decimal]],
    output_path: Path,
    *,
    release_version: str,
    date_range_label: str,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required. Install it with: "
            "python3 -m pip install matplotlib"
        ) from exc

    band_values = [
        [float(value) for value in values_by_band[band]]
        for band in AGE_BANDS
    ]
    labels = [AGE_BAND_DISPLAY_LABELS[band] for band in AGE_BANDS]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(13, 7))
    ax.stackplot(dates, band_values, labels=labels)

    ax.set_title(
        "Open Bitcoin Metrics: Bitcoin Days Destroyed by Age Band\n"
        f"{date_range_label} - {release_version}"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("BTC-days")
    ax.grid(True, alpha=0.3)

    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        borderaxespad=0.0,
        title="Age band",
    )

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a stacked area plot from the wide OBM "
            "CDD age-band CSV."
        )
    )

    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to obm_cdd_age_band_btcxdays_daily CSV file.",
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output PNG file path.",
    )

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        dates, values_by_band, release_version, date_range_label = read_cdd_age_band_csv(
            args.csv_file
        )

        plot_stacked_area(
            dates,
            values_by_band,
            args.output,
            release_version=release_version,
            date_range_label=date_range_label,
        )

        print(f"Read {len(dates)} observations from {args.csv_file}")
        print(f"Wrote stacked CDD age-band plot to {args.output}")

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
