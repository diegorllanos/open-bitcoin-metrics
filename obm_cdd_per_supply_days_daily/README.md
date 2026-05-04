# `obm_cdd_per_supply_days_daily`

## Overview

`obm_cdd_per_supply_days_daily` is a derived Open Bitcoin Metrics (OBM) daily series that reports Coin Days Destroyed (CDD) normalized by the outstanding Bitcoin supply.

The metric expresses the amount of coin-age destroyed on a given day relative to the total BTC supply available on that day. Its unit is **days**.

This series is useful for comparing daily CDD across periods with very different levels of Bitcoin supply. Raw CDD tends to increase mechanically as the monetary base grows. Dividing by supply produces a supply-normalized measure of daily coin-age destruction.

## Definition

For each calendar day \(t\):

```text
obm_cdd_per_supply_days_daily(t) =
    obm_cdd_btcxdays_daily(t) / obm_supply_btc_daily(t)
```

where:

- `obm_cdd_btcxdays_daily(t)` is daily Coin Days Destroyed, measured in BTC × days.
- `obm_supply_btc_daily(t)` is the outstanding Bitcoin supply, measured in BTC.

Therefore, the resulting unit is:

```text
(BTC × days) / BTC = days
```

## Interpretation

The metric can be interpreted as the daily amount of destroyed coin-age per unit of outstanding supply.

For example, a value of `0.05` means that the CDD destroyed on that day is equivalent to 0.05 days of age for each BTC in the outstanding supply, after supply normalization.

This does **not** mean that every coin moved, nor that the average coin age was 0.05 days. It is an aggregate, supply-normalized destruction measure derived from the CDD numerator.

## Input files

The script expects two existing OBM CSV files:

```text
obm_cdd_btcxdays_daily.csv
obm_supply_btc_daily.csv
```

Both files must follow the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

The expected input series are:

| Input file | Expected `series_id` | Expected unit | Frequency |
|---|---|---:|---|
| `obm_cdd_btcxdays_daily.csv` | `obm_cdd_btcxdays_daily` | `BTC-days` | `daily` |
| `obm_supply_btc_daily.csv` | `obm_supply_btc_daily` | `BTC` | `daily` |

If the existing CDD file uses a different unit spelling, for example `BTC × days`, `BTC days`, or `btcxdays`, the script should be adjusted consistently before execution.

## Output file

The script generates:

```text
obm_cdd_per_supply_days_daily.csv
```

with the standard OBM output schema:

```text
date,series_id,value,unit,frequency,release_version
```

The output fields are:

| Field | Description |
|---|---|
| `date` | Calendar date in `YYYY-MM-DD` format. |
| `series_id` | Always `obm_cdd_per_supply_days_daily`. |
| `value` | CDD per unit of supply, expressed in days. |
| `unit` | Always `days`. |
| `frequency` | Always `daily`. |
| `release_version` | OBM release version inherited from the input files. |

## Undefined values

The denominator is `obm_supply_btc_daily`. If the supply value is zero for a given date, the ratio is undefined.

In that case, the script writes an empty `value` field for that date rather than stopping with an error. This behavior is useful for the earliest Bitcoin dates or for any input interval in which the denominator is zero under the chosen supply definition.

Negative CDD or negative supply values are treated as data errors and cause the script to stop.

## Date coverage and consistency checks

The script performs the following checks before generating the output:

1. Both input files must contain the required OBM fields.
2. Each input row must have the expected `series_id`, `unit`, and `frequency`.
3. Dates must not be duplicated within either input file.
4. The requested date interval must be fully covered by the overlap of the two input files.
5. Both input files must contain complete daily coverage over the requested interval.
6. The `release_version` must be unique and consistent across both input files for the requested interval.

If any check fails, the script exits with an error message.

## Usage

Basic usage:

```bash
python3 compute_obm_cdd_per_supply_days_daily.py \
    data/daily/obm_cdd_btcxdays_daily.csv \
    data/daily/obm_supply_btc_daily.csv \
    --output data/daily/obm_cdd_per_supply_days_daily.csv
```

Restricting the date interval:

```bash
python3 compute_obm_cdd_per_supply_days_daily.py \
    data/daily/obm_cdd_btcxdays_daily.csv \
    data/daily/obm_supply_btc_daily.csv \
    --start_date 2024-01-01 \
    --end_date 2024-01-31 \
    --output data/daily/obm_cdd_per_supply_days_daily.csv
```

Generating a plot:

```bash
python3 compute_obm_cdd_per_supply_days_daily.py \
    data/daily/obm_cdd_btcxdays_daily.csv \
    data/daily/obm_supply_btc_daily.csv \
    --output data/daily/obm_cdd_per_supply_days_daily.csv \
    --plot
```

Specifying a custom plot path:

```bash
python3 compute_obm_cdd_per_supply_days_daily.py \
    data/daily/obm_cdd_btcxdays_daily.csv \
    data/daily/obm_supply_btc_daily.csv \
    --output data/daily/obm_cdd_per_supply_days_daily.csv \
    --plot \
    --plot_output figures/obm_cdd_per_supply_days_daily.png
```

## Notes

This metric is derived entirely from existing OBM series. It does not require a direct scan of the blockchain if `obm_cdd_btcxdays_daily` and `obm_supply_btc_daily` have already been generated.

The metric should be used as a supply-normalized version of daily CDD, not as a replacement for raw CDD. The two series answer related but different questions:

- `obm_cdd_btcxdays_daily` measures the absolute amount of coin-age destroyed on a day.
- `obm_cdd_per_supply_days_daily` measures that destroyed coin-age relative to the outstanding Bitcoin supply.
