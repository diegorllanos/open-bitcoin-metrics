# OBM Spent Output Value <155d in BTC (Daily)

## Series identifier

`obm_spent_value_lt155d_btc_daily`

## Script

`compute_obm_spent_value_lt155d_btc_daily.py`

## Purpose

This metric reports the daily BTC value of spent transaction outputs whose age is strictly lower than 155 days.

It is intended to complement the long-term-holder threshold series:

`obm_spent_value_ge155d_btc_daily`

Together, both series decompose the total daily spent output value into two mutually exclusive age groups:

- outputs aged less than 155 days;
- outputs aged at least 155 days.

The metric is useful for studying the movement of recently active coins, short-term-holder spending behavior, and the composition of daily spent value by output age.

## Definition

Let \(S_d\) denote the set of previous transaction outputs spent by non-coinbase transaction inputs in blocks assigned to UTC calendar day \(d\). Let \(v_i\) denote the BTC value of spent output \(i\), and let \(a_i\) denote its age in days.

The daily spent output value below the 155-day threshold is defined as:

\[
\mathrm{SpentValueLT155dBTC}_d =
\sum_{i \in S_d} v_i \mathbf{1}\{a_i < 155\}.
\]

The script computes the metric as a deterministic transformation of two existing OBM series:

\[
\mathrm{SpentValueLT155dBTC}_d =
\mathrm{SpentValueBTC}_d -
\mathrm{SpentValueGE155dBTC}_d.
\]

In OBM series identifiers:

\[
\texttt{obm\_spent\_value\_lt155d\_btc\_daily}
=
\texttt{obm\_spent\_value\_btc\_daily}
-
\texttt{obm\_spent\_value\_ge155d\_btc\_daily}.
\]

## Interpretation

The series measures the amount of BTC spent on each UTC day from outputs younger than 155 days.

It is a spent-value metric, not a Coin Days Destroyed metric. Its unit is BTC, not BTC-days.

The 155-day threshold follows the common convention used in on-chain analysis to distinguish short-term-holder and long-term-holder behavior. In this metric, the threshold is applied mechanically at the spent-output level:

- outputs with age \(a_i < 155\) days are included;
- outputs with age \(a_i \geq 155\) days are excluded.

The metric is raw and UTXO-based. It does not identify users, entities, custodians, exchanges, self-transfers, or change outputs.

## Input files

The script requires two existing OBM CSV files:

1. `obm_spent_value_btc_daily.csv`
2. `obm_spent_value_ge155d_btc_daily.csv`

Both files must follow the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

The expected metadata are:

| Input file | Expected `series_id` | Expected unit | Expected frequency |
|---|---|---:|---:|
| Total spent value | `obm_spent_value_btc_daily` | `BTC` | `daily` |
| Spent value >=155d | `obm_spent_value_ge155d_btc_daily` | `BTC` | `daily` |

## Output file

By default, the script writes:

```text
obm_spent_value_lt155d_btc_daily.csv
```

The output file follows the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example row:

```text
2024-01-01,obm_spent_value_lt155d_btc_daily,123456.78901234,BTC,daily,OBM v0.1.0
```

## Output columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_spent_value_lt155d_btc_daily` |
| `value` | Daily BTC value of spent outputs aged less than 155 days |
| `unit` | `BTC` |
| `frequency` | `daily` |
| `release_version` | OBM release version inherited from the source interval |

## Usage

Basic usage:

```bash
python3 compute_obm_spent_value_lt155d_btc_daily.py \
  obm_spent_value_btc_daily.csv \
  obm_spent_value_ge155d_btc_daily.csv \
  --output obm_spent_value_lt155d_btc_daily.csv
```

With an explicit date interval:

```bash
python3 compute_obm_spent_value_lt155d_btc_daily.py \
  obm_spent_value_btc_daily.csv \
  obm_spent_value_ge155d_btc_daily.csv \
  --start_date 2009-01-03 \
  --end_date 2025-12-31 \
  --output obm_spent_value_lt155d_btc_daily.csv
```

With plot generation:

```bash
python3 compute_obm_spent_value_lt155d_btc_daily.py \
  obm_spent_value_btc_daily.csv \
  obm_spent_value_ge155d_btc_daily.csv \
  --output obm_spent_value_lt155d_btc_daily.csv \
  --plot \
  --plot_output obm_spent_value_lt155d_btc_daily.png
```

## Command-line arguments

### Positional arguments

| Argument | Description |
|---|---|
| `spent_value_csv` | Path to the `obm_spent_value_btc_daily` CSV file |
| `spent_value_ge155d_csv` | Path to the `obm_spent_value_ge155d_btc_daily` CSV file |

### Optional arguments

| Argument | Description |
|---|---|
| `--start_date` | Start date in `YYYY-MM-DD` format, inclusive. If omitted, the first common date in both input files is used |
| `--end_date` | End date in `YYYY-MM-DD` format, inclusive. If omitted, the last common date in both input files is used |
| `--output` | Output CSV path. Default: `obm_spent_value_lt155d_btc_daily.csv` |
| `--plot` | Generate a line plot of the resulting series |
| `--plot_output` | Output path for the plot. Default: `obm_spent_value_lt155d_btc_daily.png` |
| `--negative_tolerance` | Tolerance for tiny negative values caused by decimal rounding. Default: `0.00000001` BTC |

## Method

The script performs the following steps:

1. Reads the total spent output value series.
2. Reads the spent output value aged at least 155 days series.
3. Validates the schema of both input files.
4. Checks that the input series identifiers are:
   - `obm_spent_value_btc_daily`
   - `obm_spent_value_ge155d_btc_daily`
5. Checks that both input series use unit `BTC` and frequency `daily`.
6. Determines the date interval:
   - from `--start_date` and `--end_date`, if provided;
   - otherwise, from the common overlapping interval of the two input files.
7. Verifies that both inputs contain one observation for every selected date.
8. Verifies that the selected interval does not mix different `release_version` values.
9. Computes, for each date:

   \[
   \mathrm{SpentValueLT155dBTC}_d =
   \mathrm{SpentValueBTC}_d -
   \mathrm{SpentValueGE155dBTC}_d.
   \]

10. Writes the resulting daily series using the standard OBM schema.
11. Optionally generates a line plot.

## Validation

### Validations effectively carried out by the script

The script performs the following checks automatically:

1. Verifies that both input files exist.
2. Verifies that both input files contain the required OBM columns:
   - `date`
   - `series_id`
   - `value`
   - `unit`
   - `frequency`
   - `release_version`
3. Verifies that each source file contains at least one observation.
4. Verifies that all dates use the `YYYY-MM-DD` format.
5. Verifies that each date appears at most once in each input file.
6. Verifies that source values are valid decimal numbers.
7. Verifies that source values are non-negative.
8. Verifies that the first input file has series identifier `obm_spent_value_btc_daily`.
9. Verifies that the second input file has series identifier `obm_spent_value_ge155d_btc_daily`.
10. Verifies that both input files use unit `BTC`.
11. Verifies that both input files use frequency `daily`.
12. Verifies that the two input files have at least one overlapping date.
13. Verifies that the selected date interval is valid.
14. Verifies that both inputs contain every date in the selected interval.
15. Verifies that the selected interval uses a single `release_version` across both source files.
16. Computes the identity:

    \[
    \texttt{obm\_spent\_value\_lt155d\_btc\_daily}
    =
    \texttt{obm\_spent\_value\_btc\_daily}
    -
    \texttt{obm\_spent\_value\_ge155d\_btc\_daily}.
    \]

17. Aborts if the computed value is materially negative.
18. Sets tiny negative values to zero only when their absolute value is below the configured decimal-rounding tolerance.

### Recommended additional checks

The following checks are recommended for formal releases, but are not fully performed by the script itself:

1. Independently verify that `obm_spent_value_ge155d_btc_daily` was computed using the same age definition and timestamp convention as `obm_spent_value_btc_daily`.
2. Verify that the 155-day threshold is implemented as:
   \[
   a_i \geq 155
   \]
   for the long-term series, so that the short-term complement is:
   \[
   a_i < 155.
   \]
3. Randomly sample selected dates and recompute the metric directly from the spent-output index or full-node-derived database.
4. Confirm the decomposition identity over the full release interval:
   \[
   \texttt{obm\_spent\_value\_btc\_daily}
   =
   \texttt{obm\_spent\_value\_lt155d\_btc\_daily}
   +
   \texttt{obm\_spent\_value\_ge155d\_btc\_daily}.
   \]
5. Compare aggregate behavior with public age-band metrics, such as spent volume by age or long-term-holder spent-volume indicators, when available.
6. Inspect large daily spikes manually, because they may correspond to exchange reorganizations, custodial wallet movements, self-transfers, or other non-payment activity.
7. Confirm that all source files correspond to the same OBM release and have not been manually edited.
8. Review whether decimal precision in the source files is sufficient for long cumulative comparisons.

## Relationship with other OBM series

This metric is part of the spent-value age-threshold family:

| Series | Meaning |
|---|---|
| `obm_spent_value_btc_daily` | Total daily spent output value in BTC |
| `obm_spent_value_lt155d_btc_daily` | Daily spent output value from outputs aged less than 155 days |
| `obm_spent_value_ge155d_btc_daily` | Daily spent output value from outputs aged at least 155 days |
| `obm_spent_value_ge365d_btc_daily` | Daily spent output value from outputs aged at least 365 days |

The key decomposition is:

\[
\texttt{obm\_spent\_value\_btc\_daily}
=
\texttt{obm\_spent\_value\_lt155d\_btc\_daily}
+
\texttt{obm\_spent\_value\_ge155d\_btc\_daily}.
\]

The 365-day threshold series is nested within the 155-day threshold series:

\[
\texttt{obm\_spent\_value\_ge365d\_btc\_daily}
\leq
\texttt{obm\_spent\_value\_ge155d\_btc\_daily}.
\]

This relationship should hold date by date, up to rounding.

## Known limitations

1. The metric is derived from two existing OBM CSV files and is not an independent full-node reconstruction.
2. It inherits the timestamp convention, age definition, source-data coverage, and release version of the input series.
3. It is raw and UTXO-based. It does not identify entities, exchanges, custodians, self-transfers, or change outputs.
4. It should not be interpreted as payment volume, user activity, or economic transfer volume.
5. It depends on the correctness and consistency of both source series.
6. It uses a hard 155-day boundary. Other providers may use smoothed, probabilistic, or entity-level long-term-holder definitions.
7. It reports BTC value, not fiat value.
8. It does not distinguish whether recently active coins are being spent for payments, exchange activity, internal wallet management, consolidation, or custodial restructuring.

## Reproducibility notes

This script is deterministic. Given the same two input CSV files, date interval, and rounding tolerance, it will always produce the same output.

The script does not query Bitcoin Core, does not use third-party APIs, and does not require access to the spent-output index. It should therefore be run after the two source series have already been generated and validated.

## Suggested citation label

`obm_spent_value_lt155d_btc_daily`
