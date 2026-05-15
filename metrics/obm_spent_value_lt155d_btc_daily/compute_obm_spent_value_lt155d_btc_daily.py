#!/usr/bin/env python3
"""
compute_obm_spent_value_lt155d_btc_daily.py

Compute OBM daily spent output value for outputs younger than 155 days.

Series:
    obm_spent_value_lt155d_btc_daily

Definition:
    For each UTC day d,

        SpentValueLT155dBTC_d =
            SpentValueBTC_d - SpentValueGE155dBTC_d

    where:
        obm_spent_value_btc_daily       = total daily spent output value in BTC
        obm_spent_value_ge155d_btc_daily = daily spent output value in BTC
                                          for outputs aged >= 155 days

The resulting series measures the BTC value of spent outputs whose age is
strictly less than 155 days. It is a derived metric and does not query
Bitcoin Core directly.

Input files must follow the standard OBM CSV schema:

    date, series_id, value, unit, frequency, release_version

Dates are interpreted as UTC dates in YYYY-MM-DD format.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# High precision is useful when subtracting BTC values stored as decimals.
getcontext().prec = 50


OUTPUT_SERIES_ID = "obm_spent_value_lt155d_btc_daily"
TOTAL_SPENT_SERIES_ID = "obm_spent_value_btc_daily"
GE155_SPENT_SERIES_ID = "obm_spent_value_ge155d_btc_daily"

REQUIRED_COLUMNS = [
    "date",
    "series_id",
    "value",
    "unit",
    "frequency",
    "release_version",
]

OUTPUT_UNIT = "BTC"
OUTPUT_FREQUENCY = "daily"


@dataclass(frozen=True)
class Observation:
    date: date
    series_id: str
    value: Decimal
    unit: str
    frequency: str
    release_version: str


def parse_utc_date(value: str, field_name: str = "date") -> date:
    """Parse a date in YYYY-MM-DD format."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value!r}. Expected YYYY-MM-DD.") from exc


def iter_dates(start: date, end: date) -> Iterable[date]:
    """Yield all dates from start to end, inclusive."""
    if start > end:
        raise ValueError("start_date cannot be later than end_date.")
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def parse_decimal(value: str, *, filename: Path, row_number: int) -> Decimal:
    """Parse a decimal value from a CSV value field."""
    if value is None or value == "":
        raise ValueError(
            f"{filename}: row {row_number}: value is missing. "
            "Spent-value source series must not contain missing values."
        )
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(
            f"{filename}: row {row_number}: invalid numeric value {value!r}."
        ) from exc


def read_obm_csv(path: Path) -> Dict[date, Observation]:
    """Read an OBM CSV file and return observations keyed by date."""
    if not path.exists():
        raise FileNotFoundError(f"Input file does not exist: {path}")

    observations: Dict[date, Observation] = {}

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames is None:
            raise ValueError(f"{path}: empty CSV file.")

        missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
        if missing:
            raise ValueError(f"{path}: missing required columns: {', '.join(missing)}")

        for row_number, row in enumerate(reader, start=2):
            obs_date = parse_utc_date(row["date"], "date")
            if obs_date in observations:
                raise ValueError(f"{path}: duplicate observation for date {obs_date}.")

            value = parse_decimal(row["value"], filename=path, row_number=row_number)
            if value < 0:
                raise ValueError(
                    f"{path}: row {row_number}: negative value {value}. "
                    "Spent-value source series must be non-negative."
                )

            observations[obs_date] = Observation(
                date=obs_date,
                series_id=row["series_id"],
                value=value,
                unit=row["unit"],
                frequency=row["frequency"],
                release_version=row["release_version"],
            )

    if not observations:
        raise ValueError(f"{path}: no observations found.")

    return observations


def validate_source_series(
    observations: Dict[date, Observation],
    *,
    expected_series_id: str,
    expected_unit: str,
    expected_frequency: str,
    path: Path,
) -> None:
    """Validate the series identifier, unit, and frequency of a source CSV."""
    series_ids = {obs.series_id for obs in observations.values()}
    units = {obs.unit for obs in observations.values()}
    frequencies = {obs.frequency for obs in observations.values()}

    if series_ids != {expected_series_id}:
        raise ValueError(
            f"{path}: expected series_id {expected_series_id!r}, "
            f"found {sorted(series_ids)!r}."
        )

    if units != {expected_unit}:
        raise ValueError(
            f"{path}: expected unit {expected_unit!r}, found {sorted(units)!r}."
        )

    if frequencies != {expected_frequency}:
        raise ValueError(
            f"{path}: expected frequency {expected_frequency!r}, "
            f"found {sorted(frequencies)!r}."
        )


def infer_interval(
    total_obs: Dict[date, Observation],
    ge155_obs: Dict[date, Observation],
    start_date: Optional[date],
    end_date: Optional[date],
) -> Tuple[date, date]:
    """Infer or validate the selected date interval."""
    total_dates = set(total_obs)
    ge155_dates = set(ge155_obs)
    common_dates = total_dates & ge155_dates

    if not common_dates:
        raise ValueError("The two input files have no overlapping dates.")

    inferred_start = min(common_dates)
    inferred_end = max(common_dates)

    start = start_date or inferred_start
    end = end_date or inferred_end

    if start > end:
        raise ValueError("start_date cannot be later than end_date.")

    return start, end


def validate_complete_interval(
    observations: Dict[date, Observation],
    *,
    start: date,
    end: date,
    path: Path,
) -> None:
    """Ensure the source contains exactly one observation for every selected date."""
    missing_dates = [d for d in iter_dates(start, end) if d not in observations]
    if missing_dates:
        preview = ", ".join(str(d) for d in missing_dates[:10])
        suffix = "" if len(missing_dates) <= 10 else f", ... ({len(missing_dates)} missing dates)"
        raise ValueError(f"{path}: missing observations for selected dates: {preview}{suffix}")


def infer_release_version(
    total_obs: Dict[date, Observation],
    ge155_obs: Dict[date, Observation],
    *,
    start: date,
    end: date,
) -> str:
    """Infer a single release_version from both source files over the selected interval."""
    versions = set()
    for d in iter_dates(start, end):
        versions.add(total_obs[d].release_version)
        versions.add(ge155_obs[d].release_version)

    if len(versions) != 1:
        raise ValueError(
            "Selected interval mixes release_version values across source files: "
            f"{sorted(versions)!r}."
        )

    return next(iter(versions))


def compute_lt155_series(
    total_obs: Dict[date, Observation],
    ge155_obs: Dict[date, Observation],
    *,
    start: date,
    end: date,
    negative_tolerance: Decimal,
) -> List[Tuple[date, Decimal]]:
    """Compute total spent value minus >=155d spent value for each selected date."""
    output: List[Tuple[date, Decimal]] = []

    for d in iter_dates(start, end):
        total_value = total_obs[d].value
        ge155_value = ge155_obs[d].value
        lt155_value = total_value - ge155_value

        if lt155_value < 0:
            # Allow a tiny negative value only when it is clearly rounding noise.
            if abs(lt155_value) <= negative_tolerance:
                lt155_value = Decimal("0")
            else:
                raise ValueError(
                    f"Computed negative value on {d}: "
                    f"total={total_value}, ge155={ge155_value}, "
                    f"lt155={lt155_value}. "
                    "This indicates inconsistent source files or different definitions."
                )

        output.append((d, lt155_value))

    return output


def decimal_to_string(value: Decimal) -> str:
    """Format Decimal values without scientific notation."""
    if value == 0:
        return "0"
    normalized = value.normalize()
    # Avoid scientific notation for very small values.
    return format(normalized, "f")


def write_obm_csv(
    rows: Sequence[Tuple[date, Decimal]],
    *,
    output_path: Path,
    release_version: str,
) -> None:
    """Write the derived series using the standard OBM schema."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(REQUIRED_COLUMNS)

        for obs_date, value in rows:
            writer.writerow(
                [
                    obs_date.isoformat(),
                    OUTPUT_SERIES_ID,
                    decimal_to_string(value),
                    OUTPUT_UNIT,
                    OUTPUT_FREQUENCY,
                    release_version,
                ]
            )


def plot_series(
    rows: Sequence[Tuple[date, Decimal]],
    *,
    plot_output: Path,
    title: str,
) -> None:
    """Generate a simple line plot if requested."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required for --plot but is not installed."
        ) from exc

    dates = [d for d, _ in rows]
    values = [float(v) for _, v in rows]

    plot_output.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(12, 6))
    plt.plot(dates, values)
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel("BTC")
    plt.tight_layout()
    plt.savefig(plot_output, dpi=150)
    plt.close()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute obm_spent_value_lt155d_btc_daily from "
            "obm_spent_value_btc_daily and obm_spent_value_ge155d_btc_daily."
        )
    )

    parser.add_argument(
        "spent_value_csv",
        type=Path,
        help="Path to obm_spent_value_btc_daily CSV file.",
    )
    parser.add_argument(
        "spent_value_ge155d_csv",
        type=Path,
        help="Path to obm_spent_value_ge155d_btc_daily CSV file.",
    )
    parser.add_argument(
        "--start_date",
        type=lambda s: parse_utc_date(s, "start_date"),
        default=None,
        help=(
            "Start date in YYYY-MM-DD format, inclusive. "
            "If omitted, the first common date in both input files is used."
        ),
    )
    parser.add_argument(
        "--end_date",
        type=lambda s: parse_utc_date(s, "end_date"),
        default=None,
        help=(
            "End date in YYYY-MM-DD format, inclusive. "
            "If omitted, the last common date in both input files is used."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("obm_spent_value_lt155d_btc_daily.csv"),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate a plot of the resulting series.",
    )
    parser.add_argument(
        "--plot_output",
        type=Path,
        default=Path("obm_spent_value_lt155d_btc_daily.png"),
        help="Output path for the plot when --plot is used.",
    )
    parser.add_argument(
        "--negative_tolerance",
        type=Decimal,
        default=Decimal("0.00000001"),
        help=(
            "Tolerance for tiny negative values caused by decimal rounding. "
            "Values below this absolute threshold are set to zero."
        ),
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        total_obs = read_obm_csv(args.spent_value_csv)
        ge155_obs = read_obm_csv(args.spent_value_ge155d_csv)

        validate_source_series(
            total_obs,
            expected_series_id=TOTAL_SPENT_SERIES_ID,
            expected_unit=OUTPUT_UNIT,
            expected_frequency=OUTPUT_FREQUENCY,
            path=args.spent_value_csv,
        )
        validate_source_series(
            ge155_obs,
            expected_series_id=GE155_SPENT_SERIES_ID,
            expected_unit=OUTPUT_UNIT,
            expected_frequency=OUTPUT_FREQUENCY,
            path=args.spent_value_ge155d_csv,
        )

        start, end = infer_interval(
            total_obs,
            ge155_obs,
            args.start_date,
            args.end_date,
        )

        validate_complete_interval(total_obs, start=start, end=end, path=args.spent_value_csv)
        validate_complete_interval(ge155_obs, start=start, end=end, path=args.spent_value_ge155d_csv)

        release_version = infer_release_version(
            total_obs,
            ge155_obs,
            start=start,
            end=end,
        )

        rows = compute_lt155_series(
            total_obs,
            ge155_obs,
            start=start,
            end=end,
            negative_tolerance=args.negative_tolerance,
        )

        write_obm_csv(rows, output_path=args.output, release_version=release_version)

        if args.plot:
            plot_series(
                rows,
                plot_output=args.plot_output,
                title=(
                    "OBM Spent Output Value <155d "
                    f"({start.isoformat()} to {end.isoformat()})"
                ),
            )

        total_btc = sum((v for _, v in rows), Decimal("0"))
        print(f"Wrote {len(rows)} observations to {args.output}")
        print(f"Series ID: {OUTPUT_SERIES_ID}")
        print(f"Date range: {start.isoformat()} to {end.isoformat()}")
        print(f"Total value over selected interval: {decimal_to_string(total_btc)} BTC")
        if args.plot:
            print(f"Wrote plot to {args.plot_output}")

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
