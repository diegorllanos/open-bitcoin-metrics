# Open Bitcoin Metrics: Spent Output Value Younger Than 155 Days in BTC

This repository provides the following time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_spent_value_lt155d_btc_daily
```

The series reports the daily BTC value of spent outputs whose age is strictly less than 155 days.

The computation script is:

```text
compute_obm_spent_value_lt155d_btc_daily.py
```

This is a derived metric. It does not query Bitcoin Core and does not read the OBM spent-output indexer database directly. Instead, it derives the series from two already generated OBM CSV files:

```text
obm_spent_value_btc_daily
obm_spent_value_ge155d_btc_daily
```

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_spent_value_lt155d_btc_daily` |
| Display name | Spent output value younger than 155 days in BTC |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Derived from existing OBM CSV files |
| External data required | No |
| Main use | Short-term spent value, UTXO-age decomposition, counterpart to >=155-day spent value |

## Definition

`obm_spent_value_lt155d_btc_daily` measures the BTC value of outputs spent on a given UTC calendar day whose age is strictly less than 155 days.

The script computes the metric as a deterministic difference between two source series:

```text
SpentValueLT155dBTC_d =
    SpentValueBTC_d - SpentValueGE155dBTC_d
```

where `SpentValueBTC_d` is the total daily spent output value, corresponding to `obm_spent_value_btc_daily`, and `SpentValueGE155dBTC_d` is the daily spent output value for outputs aged at least 155 days, corresponding to `obm_spent_value_ge155d_btc_daily`.

Therefore:

```text
obm_spent_value_lt155d_btc_daily =
    obm_spent_value_btc_daily -
    obm_spent_value_ge155d_btc_daily
```

The threshold is strict on the output side: outputs aged less than 155 days are included, while outputs aged 155 days or more are excluded.

## Interpretation

`obm_spent_value_lt155d_btc_daily` measures the BTC value of relatively young outputs consumed on-chain each day.

This metric is useful for:

- separating younger spent value from older spent value;
- complementing the >=155-day spent-value series;
- studying short-term-holder or recently active coin turnover;
- analyzing UTXO-flow dynamics by age threshold;
- computing shares of spent value below and above the 155-day boundary;
- building empirical datasets where young-output activity and old-output activity are treated separately.

The metric should not be interpreted as entity-adjusted short-term-holder selling. It is a raw spent-output measure. It does not identify users, entities, custodians, exchanges, self-transfers, change outputs, or payment purpose.

## Relationship with the >=155-day source series

The metric is designed as the complement of the >=155-day spent-value series within total spent value.

For each UTC date `d`, the intended decomposition is:

```text
obm_spent_value_btc_daily =
    obm_spent_value_lt155d_btc_daily +
    obm_spent_value_ge155d_btc_daily
```

Equivalently:

```text
obm_spent_value_lt155d_btc_daily =
    obm_spent_value_btc_daily -
    obm_spent_value_ge155d_btc_daily
```

This relationship is exact when all series are generated from the same definitions, timestamp convention, and release version, apart from negligible decimal rounding effects.

## Data source and input requirements

The script requires two positional input files:

```text
spent_value_csv
spent_value_ge155d_csv
```

The first file must contain the source series:

```text
obm_spent_value_btc_daily
```

The second file must contain the source series:

```text
obm_spent_value_ge155d_btc_daily
```

Both files must follow the standard OBM CSV schema:

```text
date,series_id,value,unit,frequency,release_version
```

Dates are interpreted as UTC dates in `YYYY-MM-DD` format. Source values must be non-missing, numeric, and non-negative.

The script validates that the source series have:

| Source file | Expected `series_id` | Expected `unit` | Expected `frequency` |
|---|---|---|---|
| total spent value | `obm_spent_value_btc_daily` | `BTC` | `daily` |
| >=155-day spent value | `obm_spent_value_ge155d_btc_daily` | `BTC` | `daily` |

The selected interval can be supplied explicitly through:

```text
--start_date
--end_date
```

If either is omitted, the script uses the first or last common date available in both input files.

## Data format

The output CSV file follows the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_spent_value_lt155d_btc_daily,370027.00000000,BTC,daily,OBM v0.1.0
2024-01-02,obm_spent_value_lt155d_btc_daily,341900.00000000,BTC,daily,OBM v0.1.0
```

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_spent_value_lt155d_btc_daily` |
| `value` | BTC value of spent outputs younger than 155 days |
| `unit` | Measurement unit: `BTC` |
| `frequency` | Observation frequency: `daily` |
| `release_version` | OBM dataset release version inferred from the source files |

## Reproducibility

The metric is generated as a deterministic transformation of two source OBM CSV files.

For the selected date interval, the script:

1. reads the total spent-value CSV file;
2. reads the >=155-day spent-value CSV file;
3. verifies that both files contain the required OBM schema columns;
4. verifies that source values are numeric, non-missing, and non-negative;
5. verifies that each file contains no duplicate dates;
6. verifies the expected `series_id`, `unit`, and `frequency` for each source file;
7. infers or validates the selected date interval;
8. verifies that both source files contain one observation for every date in the selected interval;
9. verifies that the selected interval uses a single common `release_version`;
10. computes `total spent value - >=155-day spent value` for each date;
11. allows tiny negative values only within the configured decimal tolerance and sets them to zero;
12. raises an error for larger negative values;
13. writes the resulting time series to CSV using the standard OBM schema;
14. optionally generates a plot.

Because this metric is derived from already generated CSV files, it can be reproduced without access to Bitcoin Core or to the SQLite indexer database, provided that the two source series are available.

## Typical script usage

Generate the CSV file:

```bash
python3 compute_obm_spent_value_lt155d_btc_daily.py \
  data/daily/obm_spent_value_btc_daily.csv \
  data/daily/obm_spent_value_ge155d_btc_daily.csv \
  --start_date 2009-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_spent_value_lt155d_btc_daily.csv
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_spent_value_lt155d_btc_daily.py \
  data/daily/obm_spent_value_btc_daily.csv \
  data/daily/obm_spent_value_ge155d_btc_daily.csv \
  --start_date 2009-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_spent_value_lt155d_btc_daily.csv \
  --plot \
  --plot_output figures/obm_spent_value_lt155d_btc_daily.png
```

If `--start_date` and `--end_date` are omitted, the script uses the first and last common dates available in both input files.

## Command-line arguments

| Argument | Description |
|---|---|
| `spent_value_csv` | Path to the `obm_spent_value_btc_daily` CSV file |
| `spent_value_ge155d_csv` | Path to the `obm_spent_value_ge155d_btc_daily` CSV file |
| `--start_date` | Optional starting UTC date, inclusive, in `YYYY-MM-DD` format |
| `--end_date` | Optional ending UTC date, inclusive, in `YYYY-MM-DD` format |
| `--output` | Output CSV file path |
| `--plot` | Generate a plot of the resulting series |
| `--plot_output` | Output path for the plot when `--plot` is used |
| `--negative_tolerance` | Tolerance for tiny negative values caused by decimal rounding |

The default output file is:

```text
obm_spent_value_lt155d_btc_daily.csv
```

The default plot output file is:

```text
obm_spent_value_lt155d_btc_daily.png
```

The default negative tolerance is:

```text
0.00000001
```

Values below this absolute threshold are treated as rounding noise and set to zero.

## Requirements

The script assumes:

- Python 3;
- two existing OBM CSV files with the standard schema;
- matching daily frequency and BTC unit in both source files;
- compatible release versions across the selected interval;
- `matplotlib`, only if plot generation is requested.

This script does not require:

- a running Bitcoin Core node;
- access to the Bitcoin Core JSON-RPC interface;
- direct block scanning;
- direct SQLite indexer access;
- direct previous-output reconstruction;
- address extraction;
- user clustering;
- entity identification;
- external price data;
- third-party APIs.

## Missing-date convention

This script does not create missing dates automatically from sparse input files. Instead, it requires both input files to contain one observation for every date in the selected interval.

If either input file lacks any selected date, the script raises an error. This prevents silently producing an incomplete decomposition.

For valid inputs, the output contains one observation for each calendar date in the selected interval.

## Precision

The script uses Python's `Decimal` type with high precision when subtracting BTC values. This reduces the risk of binary floating-point artifacts.

The output values are formatted without scientific notation. Tiny negative values whose absolute magnitude is no greater than `--negative_tolerance` are set to zero. Larger negative values cause the script to abort, because they indicate inconsistent source files or incompatible definitions.

## Validation

Validation is divided into two groups: checks performed directly by the script, and additional checks that are advisable for release preparation or independent auditing.

### Checks performed by the script

The script performs the following checks during execution:

- verifies that each input file exists;
- verifies that each input file is non-empty;
- verifies that both input files contain the required OBM schema columns;
- verifies that all source `value` fields are present and parseable as decimals;
- verifies that all source values are non-negative;
- verifies that each source file contains no duplicate dates;
- verifies that the first source file has `series_id = obm_spent_value_btc_daily`;
- verifies that the second source file has `series_id = obm_spent_value_ge155d_btc_daily`;
- verifies that both source files use unit `BTC`;
- verifies that both source files use frequency `daily`;
- verifies that the two source files have at least one overlapping date;
- verifies that `--start_date` is not later than `--end_date`;
- verifies that both source files contain complete observations for every date in the selected interval;
- verifies that the selected interval uses one common `release_version` across both source files;
- computes the derived value as total spent value minus >=155-day spent value;
- raises an error if the computed value is negative beyond the configured tolerance;
- clamps tiny negative values within the configured tolerance to zero;
- writes the output using the standard OBM schema;
- optionally generates a plot when `--plot` is used.

These checks ensure that the derived series is computed from complete, compatible, non-negative, same-release source series.

### Recommended additional checks

The following checks are not performed automatically by the script, but are recommended before publishing a release or using the series in empirical work:

- verify that every requested date appears exactly once in the output CSV;
- verify that all output values are non-negative;
- verify the decomposition:
  ```text
  obm_spent_value_btc_daily =
      obm_spent_value_lt155d_btc_daily +
      obm_spent_value_ge155d_btc_daily
  ```
  for every date in the selected interval;
- verify that:
  ```text
  0 <= obm_spent_value_lt155d_btc_daily <= obm_spent_value_btc_daily
  ```
  for every date;
- verify that:
  ```text
  0 <= obm_spent_value_ge155d_btc_daily <= obm_spent_value_btc_daily
  ```
  for every date;
- inspect days with unusually large young-output spent value and compare them with transaction-count and spent-output-count metrics;
- compare the share:
  ```text
  obm_spent_value_lt155d_btc_daily / obm_spent_value_btc_daily
  ```
  against the complementary >=155-day share when total spent value is positive;
- check that the output `release_version` field is consistent with the two source files;
- document any definition differences if comparing with external short-term-holder or young-coin spent-value metrics.

External comparisons should be interpreted cautiously because providers may differ in timestamp convention, age-threshold definition, entity adjustment, change-output treatment, transfer-value definition, and historical edge-case handling.

## Relationship with other OBM metrics

This metric is closely related to:

```text
obm_spent_value_btc_daily
obm_spent_value_ge155d_btc_daily
obm_cdd_155d_btc_daily
obm_cdd_365d_btc_daily
obm_dormancy_days_daily
```

Its primary relationship is the decomposition:

```text
obm_spent_value_btc_daily =
    obm_spent_value_lt155d_btc_daily +
    obm_spent_value_ge155d_btc_daily
```

The metric can also be used to construct a young-output spent-value share:

```text
obm_spent_value_lt155d_btc_daily /
obm_spent_value_btc_daily
```

for dates where total spent value is positive.

If `obm_spent_value_ge155d_btc_daily` is aligned with `obm_cdd_155d_btc_daily`, then the following equivalence should hold:

```text
obm_spent_value_ge155d_btc_daily =
obm_cdd_155d_btc_daily
```

provided that both series use the same 155-day threshold definition, timestamp convention, and release version. In that case, the present metric is also the complement of `obm_cdd_155d_btc_daily` within total spent value.

## Known limitations

Take into account that this metric:

- is a derived metric, not a direct blockchain or indexer export;
- depends on the correctness and completeness of both source CSV files;
- inherits the UTC block-timestamp convention of the source series;
- inherits the 155-day threshold convention of the >=155-day source series;
- is a raw spent-output metric, not an entity-adjusted measure;
- includes self-transfers, change-related activity, batching, consolidation transactions, and custodial wallet management through the underlying spent-value series;
- does not identify users, entities, exchanges, custodians, or payment purpose;
- reports BTC value, not fiat-denominated value;
- may change if either source series definition or release version changes.

Despite these limitations, `obm_spent_value_lt155d_btc_daily` is a useful OBM derived series. It provides the young-output counterpart to the >=155-day spent-value series and supports decomposition of daily spent value into younger and older spent-output components.

## Suggested citation

A formal citation will be added once the dataset receives a DOI.

For now, please cite this repository as:

```text
Llanos, D. R. Open Bitcoin Metrics: Reproducible Full-Node-Derived Bitcoin On-Chain Time Series
Metric: Spent Output Value Younger Than 155 Days in BTC (obm_spent_value_lt155d_btc_daily).
GitHub repository, version OBM v0.1.0.
https://github.com/diegorllanos/open-bitcoin-metrics/
```

Because this metric is derived from other OBM series, users should also cite or reference the documentation for the source series when reproducibility details are relevant.

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
