#!/usr/bin/env python3
"""
compute_obm_liveliness_ratio_daily.py

Compute the OBM daily liveliness ratio:

    obm_liveliness_ratio_daily

from two existing OBM daily CSV files:

    obm_cdd_btcxdays_daily.csv
    obm_supply_btc_daily.csv

Definition:

    Liveliness_d =
        cumulative CDD up to day d
        /
        cumulative coin days created up to day d

where:

    cumulative CDD up to day d =
        sum_{tau <= d} obm_cdd_btcxdays_daily_tau

and:

    cumulative coin days created up to day d =
        sum_{tau <= d} obm_supply_btc_daily_tau

This implementation uses daily supply as the daily coin-day-creation base.

Important missing-date convention:

    obm_cdd_btcxdays_daily is a daily flow. If a selected date is missing
    from the CDD source file, this script treats daily CDD as zero for that
    date.

    obm_supply_btc_daily is the denominator source. It must contain one
    observation for every selected date.

Input files must follow the standard OBM scalar CSV schema:

    date,series_id,value,unit,frequency,release_version

Dates are interpreted as UTC dates in YYYY-MM-DD format.

Output schema:

    date,series_id,value,unit,frequency,release_version

Missing or zero cumulative coin-days-created denominators are exported as NaN,
because the ratio is undefined in that case.
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


getcontext().prec = 50


OUTPUT_SERIES_ID = "obm_liveliness_ratio_daily"
CDD_SERIES_ID = "obm_cdd_btcxdays_daily"
SUPPLY_SERIES_ID = "obm_supply_btc_daily"

CDD_UNIT = "BTC-days"
SUPPLY_UNIT = "BTC"
OUTPUT_UNIT = "ratio"

FREQUENCY = "daily"

REQUIRED_COLUMNS = [
    "date",
    "series_id",
    "value",
    "unit",
    "frequency",
    "release_version",
]

MISSING_VALUE = "NaN"


@dataclass(frozen=True)
class Observation:
    date: date
    series_id: str
    value: Decimal
    unit: str
    frequency: str
    release_version: str


def parse_utc_date(value: str, field_name: str = "date") -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value!r}. Expected YYYY-MM-DD.") from exc


def iter_dates(start: date, end: date) -> Iterable[date]:
    if start > end:
        raise ValueError("start_date cannot be later than end_date.")

    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def parse_decimal(value: str, *, filename: Path, row_number: int) -> Decimal:
    if value is None or value.strip() == "":
        raise ValueError(
            f"{filename}: row {row_number}: value is missing. "
            "Source series must not contain missing values."
        )

    if value.strip().lower() == "nan":
        raise ValueError(
            f"{filename}: row {row_number}: value is NaN. "
            "Source series must not contain NaN values."
        )

    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(
            f"{filename}: row {row_number}: invalid numeric value {value!r}."
        ) from exc


def read_obm_csv(path: Path) -> Dict[date, Observation]:
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
                    "Source series must be non-negative."
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
            f"{path}: expected unit {expected_unit!r}, "
            f"found {sorted(units)!r}."
        )

    if frequencies != {expected_frequency}:
        raise ValueError(
            f"{path}: expected frequency {expected_frequency!r}, "
            f"found {sorted(frequencies)!r}."
        )


def infer_interval(
    cdd_obs: Dict[date, Observation],
    supply_obs: Dict[date, Observation],
    start_date: Optional[date],
    end_date: Optional[date],
) -> Tuple[date, date]:
    """
    Infer or validate the selected date interval.

    Since CDD may be sparse, the inferred interval is based on the supply
    series. User-provided dates override this default.
    """
    if not supply_obs:
        raise ValueError("The supply input file has no observations.")

    inferred_start = min(supply_obs)
    inferred_end = max(supply_obs)

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
    series_label: str,
) -> None:
    """Ensure the source contains exactly one observation for every selected date."""
    missing_dates = [d for d in iter_dates(start, end) if d not in observations]

    if missing_dates:
        preview = ", ".join(str(d) for d in missing_dates[:10])
        suffix = "" if len(missing_dates) <= 10 else f", ... ({len(missing_dates)} missing dates)"
        raise ValueError(
            f"{path}: {series_label}: missing observations for selected dates: "
            f"{preview}{suffix}"
        )


def infer_release_version(
    cdd_obs: Dict[date, Observation],
    supply_obs: Dict[date, Observation],
    *,
    start: date,
    end: date,
) -> str:
    """
    Infer a single release_version from source files over the selected interval.

    Supply must be complete. CDD may be sparse, so missing CDD dates do not
    contribute a release_version. If CDD observations are present inside the
    selected interval, their release_version must agree with supply.
    """
    versions = set()

    for d in iter_dates(start, end):
        versions.add(supply_obs[d].release_version)
        if d in cdd_obs:
            versions.add(cdd_obs[d].release_version)

    if len(versions) != 1:
        raise ValueError(
            "Selected interval mixes release_version values across source files: "
            f"{sorted(versions)!r}."
        )

    return next(iter(versions))


def compute_liveliness_series(
    cdd_obs: Dict[date, Observation],
    supply_obs: Dict[date, Observation],
    *,
    start: date,
    end: date,
) -> List[Tuple[date, Optional[Decimal], Decimal, Decimal, Decimal, Decimal]]:
    """
    Compute daily cumulative CDD, cumulative coin-days created, and liveliness.

    Returns a list of tuples:

        (
            date,
            liveliness,
            daily_cdd,
            daily_supply,
            cumulative_cdd,
            cumulative_coin_days_created,
        )

    Missing CDD dates are treated as daily_cdd = 0.
    The liveliness value is None when the cumulative denominator is zero.
    """
    rows: List[Tuple[date, Optional[Decimal], Decimal, Decimal, Decimal, Decimal]] = []

    cumulative_cdd = Decimal("0")
    cumulative_coin_days_created = Decimal("0")

    for d in iter_dates(start, end):
        daily_cdd = cdd_obs[d].value if d in cdd_obs else Decimal("0")
        daily_supply = supply_obs[d].value

        cumulative_cdd += daily_cdd
        cumulative_coin_days_created += daily_supply

        if cumulative_coin_days_created == 0:
            liveliness = None
        else:
            liveliness = cumulative_cdd / cumulative_coin_days_created

        rows.append(
            (
                d,
                liveliness,
                daily_cdd,
                daily_supply,
                cumulative_cdd,
                cumulative_coin_days_created,
            )
        )

    return rows


def decimal_to_string(value: Decimal, decimal_places: Optional[int] = None) -> str:
    if decimal_places is not None:
        quant = Decimal("1").scaleb(-decimal_places)
        return format(value.quantize(quant), "f")

    if value == 0:
        return "0"

    return format(value.normalize(), "f")


def write_obm_csv(
    rows: Sequence[Tuple[date, Optional[Decimal], Decimal, Decimal, Decimal, Decimal]],
    *,
    output_path: Path,
    release_version: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(REQUIRED_COLUMNS)

        for obs_date, liveliness, _, _, _, _ in rows:
            if liveliness is None:
                value = MISSING_VALUE
            else:
                value = decimal_to_string(liveliness, decimal_places=12)

            writer.writerow(
                [
                    obs_date.isoformat(),
                    OUTPUT_SERIES_ID,
                    value,
                    OUTPUT_UNIT,
                    FREQUENCY,
                    release_version,
                ]
            )


def plot_series(
    rows: Sequence[Tuple[date, Optional[Decimal], Decimal, Decimal, Decimal, Decimal]],
    *,
    plot_output: Path,
    title: str,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required for --plot but is not installed."
        ) from exc

    plot_dates = []
    plot_values = []

    for obs_date, liveliness, _, _, _, _ in rows:
        if liveliness is None:
            continue
        plot_dates.append(obs_date)
        plot_values.append(float(liveliness))

    if not plot_dates:
        raise ValueError("No defined liveliness observations are available to plot.")

    plot_output.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(12, 6))
    plt.plot(plot_dates, plot_values)
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel("ratio")
    plt.tight_layout()
    plt.savefig(plot_output, dpi=150)
    plt.close()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute obm_liveliness_ratio_daily from "
            "obm_cdd_btcxdays_daily and obm_supply_btc_daily."
        )
    )

    parser.add_argument(
        "cdd_csv",
        type=Path,
        help=(
            "Path to obm_cdd_btcxdays_daily CSV file. "
            "This file may be sparse; missing selected dates are treated as zero CDD."
        ),
    )

    parser.add_argument(
        "supply_csv",
        type=Path,
        help=(
            "Path to obm_supply_btc_daily CSV file. "
            "This file must contain every selected date."
        ),
    )

    parser.add_argument(
        "--start_date",
        type=lambda s: parse_utc_date(s, "start_date"),
        default=None,
        help=(
            "Start date in YYYY-MM-DD format, inclusive. "
            "If omitted, the first date in the supply file is used."
        ),
    )

    parser.add_argument(
        "--end_date",
        type=lambda s: parse_utc_date(s, "end_date"),
        default=None,
        help=(
            "End date in YYYY-MM-DD format, inclusive. "
            "If omitted, the last date in the supply file is used."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("obm_liveliness_ratio_daily.csv"),
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
        default=Path("obm_liveliness_ratio_daily.png"),
        help="Output path for the plot when --plot is used.",
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        cdd_obs = read_obm_csv(args.cdd_csv)
        supply_obs = read_obm_csv(args.supply_csv)

        validate_source_series(
            cdd_obs,
            expected_series_id=CDD_SERIES_ID,
            expected_unit=CDD_UNIT,
            expected_frequency=FREQUENCY,
            path=args.cdd_csv,
        )

        validate_source_series(
            supply_obs,
            expected_series_id=SUPPLY_SERIES_ID,
            expected_unit=SUPPLY_UNIT,
            expected_frequency=FREQUENCY,
            path=args.supply_csv,
        )

        start, end = infer_interval(
            cdd_obs,
            supply_obs,
            args.start_date,
            args.end_date,
        )

        # Supply is the daily denominator base and must be complete.
        validate_complete_interval(
            supply_obs,
            start=start,
            end=end,
            path=args.supply_csv,
            series_label=SUPPLY_SERIES_ID,
        )

        # CDD is a daily flow. Missing selected dates are interpreted as zero CDD.
        missing_cdd_count = sum(1 for d in iter_dates(start, end) if d not in cdd_obs)

        release_version = infer_release_version(
            cdd_obs,
            supply_obs,
            start=start,
            end=end,
        )

        rows = compute_liveliness_series(
            cdd_obs,
            supply_obs,
            start=start,
            end=end,
        )

        write_obm_csv(
            rows,
            output_path=args.output,
            release_version=release_version,
        )

        if args.plot:
            plot_series(
                rows,
                plot_output=args.plot_output,
                title=(
                    "OBM Liveliness Ratio "
                    f"({start.isoformat()} to {end.isoformat()})"
                ),
            )

        defined_count = sum(1 for _, liveliness, _, _, _, _ in rows if liveliness is not None)
        missing_ratio_count = len(rows) - defined_count

        final_cum_cdd = rows[-1][4]
        final_cum_coin_days_created = rows[-1][5]
        final_liveliness = rows[-1][1]

        print(f"Wrote {len(rows)} observations to {args.output}")
        print(f"Series ID: {OUTPUT_SERIES_ID}")
        print(f"Date range: {start.isoformat()} to {end.isoformat()}")
        print(f"CDD dates treated as zero because missing: {missing_cdd_count}")
        print(f"Defined liveliness observations: {defined_count}")
        print(f"NaN liveliness observations: {missing_ratio_count}")
        print(
            "Final cumulative CDD: "
            f"{decimal_to_string(final_cum_cdd)} BTC-days"
        )
        print(
            "Final cumulative coin days created: "
            f"{decimal_to_string(final_cum_coin_days_created)} BTC-days"
        )
        if final_liveliness is None:
            print("Final liveliness: NaN")
        else:
            print(
                "Final liveliness: "
                f"{decimal_to_string(final_liveliness, decimal_places=12)}"
            )
        if args.plot:
            print(f"Wrote plot to {args.plot_output}")

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
