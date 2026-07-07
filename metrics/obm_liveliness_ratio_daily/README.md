# Open Bitcoin Metrics: Daily Liveliness Ratio

This repository provides the following derived time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_liveliness_ratio_daily
```

The series reports a daily liveliness ratio, defined as cumulative Bitcoin Days Destroyed divided by cumulative coin-days created.

The computation script is:

```text
compute_obm_liveliness_ratio_daily.py
```

or, in the revised version that treats missing CDD dates as zero:

```text
compute_obm_liveliness_ratio_daily_v2.py
```

This is a derived metric. It does not query Bitcoin Core and does not read the OBM spent-output indexer database directly. Instead, it derives the series from two already generated OBM CSV files:

```text
obm_cdd_btcxdays_daily
obm_supply_btc_daily
```

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_liveliness_ratio_daily` |
| Display name | Daily liveliness ratio |
| Unit | `ratio` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Derived from existing OBM CSV files |
| External data required | No |
| Main use | Cumulative coin-age utilization, holding/spending dynamics, macro on-chain activity |

## Definition

`obm_liveliness_ratio_daily` is defined as the ratio between cumulative Bitcoin Days Destroyed and cumulative coin-days created.

For each UTC date `d`:

```text
Liveliness_d =
    CumulativeCDD_d / CumulativeCoinDaysCreated_d
```

where:

```text
CumulativeCDD_d =
    sum_{tau <= d} CDD_tau
```

and:

```text
CumulativeCoinDaysCreated_d =
    sum_{tau <= d} SupplyBTC_tau
```

In OBM series terms:

```text
CumulativeCDD_d =
    cumulative sum of obm_cdd_btcxdays_daily
```

and:

```text
CumulativeCoinDaysCreated_d =
    cumulative sum of obm_supply_btc_daily
```

This implementation uses daily Bitcoin supply as the daily coin-day creation base. It is therefore a transparent daily approximation of the cumulative coin-day creation process.

The output unit is:

```text
ratio
```

## Interpretation

The liveliness ratio compares how much coin age has been destroyed with how much coin age has been created over the history of the network up to a given date.

A higher value indicates that a larger fraction of historically accumulated coin age has been destroyed through spending. A lower value indicates that coin age is accumulating faster than it is being destroyed.

The metric is useful for:

- summarizing long-run holding versus spending dynamics;
- measuring cumulative coin-age utilization;
- complementing Bitcoin Days Destroyed and dormancy;
- providing a slow-moving macro indicator of spent coin age;
- comparing periods of increased old-coin movement against periods of accumulation.

The metric should not be interpreted as a daily flow. It is a cumulative ratio. A large daily CDD value can move the ratio upward, but the denominator is also increasing every day as supply accumulates coin days.

## Data source and input requirements

The script requires two positional input files:

```text
cdd_csv
supply_csv
```

The first file must contain:

```text
obm_cdd_btcxdays_daily
```

The second file must contain:

```text
obm_supply_btc_daily
```

Both files must follow the standard OBM scalar CSV schema:

```text
date,series_id,value,unit,frequency,release_version
```

Dates are interpreted as UTC dates in `YYYY-MM-DD` format.

The script validates that the source series have:

| Source file | Expected `series_id` | Expected `unit` | Expected `frequency` |
|---|---|---|---|
| CDD | `obm_cdd_btcxdays_daily` | `BTC-days` | `daily` |
| Supply | `obm_supply_btc_daily` | `BTC` | `daily` |

Source values must be present, numeric, and non-negative.

## Missing-date convention

The revised script uses an asymmetric missing-date convention:

```text
missing obm_cdd_btcxdays_daily date -> daily CDD = 0
missing obm_supply_btc_daily date -> error
```

This convention is appropriate because CDD is a daily flow variable. If a selected date is absent from the CDD source file, the script interprets that day as having zero CDD.

The supply series is different. It is the denominator base used to approximate daily coin-day creation. Therefore, `obm_supply_btc_daily` must contain one observation for every selected date. If the supply file is missing a selected date, the script aborts.

If the cumulative coin-days-created denominator is zero, the liveliness ratio is undefined and the output value is written as:

```text
NaN
```

## Data format

The output CSV file follows the standard OBM scalar schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2009-01-03,obm_liveliness_ratio_daily,0.000000000000,ratio,daily,OBM v0.1.0
2009-01-04,obm_liveliness_ratio_daily,0.000000000000,ratio,daily,OBM v0.1.0
2024-01-01,obm_liveliness_ratio_daily,0.612345678901,ratio,daily,OBM v0.1.0
```

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_liveliness_ratio_daily` |
| `value` | Liveliness ratio, or `NaN` when the denominator is zero |
| `unit` | Measurement unit: `ratio` |
| `frequency` | Observation frequency: `daily` |
| `release_version` | OBM dataset release version inferred from the source files |

## Reproducibility

The metric is generated as a deterministic transformation of two source OBM CSV files.

For the selected date interval, the script:

1. reads the CDD CSV file;
2. reads the supply CSV file;
3. verifies that both files contain the required OBM schema columns;
4. verifies that source values are numeric, non-missing, and non-negative;
5. verifies that each source file contains no duplicate dates;
6. verifies the expected `series_id`, `unit`, and `frequency` for each source file;
7. infers or validates the selected date interval;
8. verifies that the supply file contains one observation for every date in the selected interval;
9. treats missing CDD observations as zero daily CDD;
10. verifies that the selected interval uses a single common `release_version`, considering supply observations and the CDD observations that are present;
11. computes cumulative CDD;
12. computes cumulative coin-days created as the cumulative sum of daily supply;
13. computes the ratio between the two cumulative quantities;
14. writes `NaN` when the cumulative denominator is zero;
15. writes the resulting time series to CSV using the standard OBM schema;
16. optionally generates a plot.

Because this metric is derived from already generated CSV files, it can be reproduced without access to Bitcoin Core or to the SQLite indexer database, provided that the two source series are available.

## Typical script usage

Generate the CSV file:

```bash
python3 compute_obm_liveliness_ratio_daily_v2.py \
  data/daily/obm_cdd_btcxdays_daily.csv \
  data/daily/obm_supply_btc_daily.csv \
  --start_date 2009-01-03 \
  --end_date 2024-01-31 \
  --output data/daily/obm_liveliness_ratio_daily.csv
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_liveliness_ratio_daily_v2.py \
  data/daily/obm_cdd_btcxdays_daily.csv \
  data/daily/obm_supply_btc_daily.csv \
  --start_date 2009-01-03 \
  --end_date 2024-01-31 \
  --output data/daily/obm_liveliness_ratio_daily.csv \
  --plot \
  --plot_output figures/obm_liveliness_ratio_daily.png
```

If `--start_date` and `--end_date` are omitted, the revised script uses the first and last dates available in the supply file.

## Command-line arguments

| Argument | Description |
|---|---|
| `cdd_csv` | Path to the `obm_cdd_btcxdays_daily` CSV file |
| `supply_csv` | Path to the `obm_supply_btc_daily` CSV file |
| `--start_date` | Optional starting UTC date, inclusive, in `YYYY-MM-DD` format |
| `--end_date` | Optional ending UTC date, inclusive, in `YYYY-MM-DD` format |
| `--output` | Output CSV file path |
| `--plot` | Generate a plot of the resulting series |
| `--plot_output` | Output path for the plot when `--plot` is used |

The default output file is:

```text
obm_liveliness_ratio_daily.csv
```

The default plot output file is:

```text
obm_liveliness_ratio_daily.png
```

## Requirements

The script assumes:

- Python 3;
- an existing `obm_cdd_btcxdays_daily` CSV file;
- an existing `obm_supply_btc_daily` CSV file;
- matching daily frequency in both source files;
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

## Precision

The script uses Python's `Decimal` type with high precision when accumulating source series and computing the ratio.

Defined output values are written with twelve decimal places:

```text
value = cumulative CDD / cumulative coin days created
```

Undefined ratios are written as:

```text
NaN
```

## Validation

Validation is divided into two groups: checks performed directly by the script, and additional checks that are advisable for release preparation or independent auditing.

### Checks performed by the script

The script performs the following checks during execution:

- verifies that each input file exists;
- verifies that each input file is non-empty;
- verifies that both input files contain the required OBM schema columns;
- verifies that all source `value` fields are present and parseable as decimals;
- rejects `NaN` values in the source files;
- verifies that all source values are non-negative;
- verifies that each source file contains no duplicate dates;
- verifies that the first source file has `series_id = obm_cdd_btcxdays_daily`;
- verifies that the first source file has unit `BTC-days`;
- verifies that the second source file has `series_id = obm_supply_btc_daily`;
- verifies that the second source file has unit `BTC`;
- verifies that both source files use frequency `daily`;
- verifies that `--start_date` is not later than `--end_date`;
- verifies that the supply file contains complete observations for every date in the selected interval;
- treats missing CDD dates as zero daily CDD;
- verifies that the selected interval uses one common `release_version`, considering all supply observations and present CDD observations;
- computes cumulative CDD;
- computes cumulative coin-days created as cumulative daily supply;
- writes `NaN` when the cumulative denominator is zero;
- writes the output using the standard OBM schema;
- optionally generates a plot when `--plot` is used.

These checks ensure that the derived series is computed from compatible source files, that the denominator source is complete, and that missing CDD flow observations are handled as zero rather than as missing ratios.

### Recommended additional checks

The following checks are not performed automatically by the script, but are recommended before publishing a release or using the series in empirical work:

- verify that every requested date appears exactly once in the output CSV;
- verify that all defined output values are non-negative;
- verify that defined output values are less than or equal to one:
  ```text
  0 <= obm_liveliness_ratio_daily <= 1
  ```
  Values above one would indicate an inconsistency between the CDD and supply conventions;
- verify that cumulative CDD is non-decreasing;
- verify that cumulative coin-days created is non-decreasing;
- verify that the liveliness ratio changes smoothly except around days with unusually large CDD;
- compare large upward movements in liveliness with `obm_cdd_btcxdays_daily`, `obm_cdd_age_band_btcxdays_daily`, and `obm_spent_value_age_band_btc_daily`;
- inspect whether long periods of low CDD coincide with declining or stable liveliness;
- check that the output `release_version` field is consistent with the two source files;
- document any definition differences when comparing with external liveliness metrics.

External comparisons should be interpreted cautiously because providers may differ in supply convention, timestamp convention, CDD definition, fractional-day treatment, treatment of lost coins, entity adjustment, and historical edge-case handling.

## Relationship with other OBM metrics

This metric is closely related to:

```text
obm_cdd_btcxdays_daily
obm_supply_btc_daily
obm_cdd_age_band_btcxdays_daily
obm_dormancy_days_daily
obm_spent_value_age_band_btc_daily
```

Its primary relationship is:

```text
obm_liveliness_ratio_daily =
    cumulative obm_cdd_btcxdays_daily /
    cumulative obm_supply_btc_daily
```

under the OBM daily approximation to coin-day creation.

A useful companion metric is aggregate CDD:

```text
obm_cdd_btcxdays_daily
```

because daily CDD shocks are the direct source of upward pressure on liveliness.

Another useful companion metric is supply:

```text
obm_supply_btc_daily
```

because supply determines the daily growth of the cumulative denominator.

## Known limitations

Take into account that this metric:

- is a derived metric, not a direct blockchain or indexer export;
- depends on the correctness and completeness of the source CDD and supply CSV files;
- treats missing CDD dates as zero daily CDD;
- requires complete supply observations across the selected interval;
- uses daily supply as an approximation to daily coin-day creation;
- inherits the UTC date convention of the source series;
- inherits the CDD convention of `obm_cdd_btcxdays_daily`;
- does not adjust for lost coins;
- is not entity-adjusted;
- is cumulative and therefore slow-moving;
- may change if either source series definition or release version changes.

The daily-supply denominator is transparent and reproducible, but it is an approximation to continuous coin-day creation. A more exact version would require tracking coin-day creation at the UTXO or block-interval level. For the OBM CSV workflow, the present definition is preferable because it is simple, auditable, and directly derived from already published OBM series.

Despite these limitations, `obm_liveliness_ratio_daily` is a useful OBM derived series. It summarizes cumulative coin-age destruction relative to cumulative coin-age creation and complements flow metrics such as CDD, dormancy, spent value, and age-band decompositions.

## Suggested citation

```text
Llanos, D. R. Open Bitcoin Metrics: Verifiable Full-Node-Derived Bitcoin Time Series for Economic Research
Metric: Daily Liveliness Ratio (obm_liveliness_ratio_daily).
ArXiv preprint, https://arxiv.org/abs/2607.03124
```

Because this metric is derived from other OBM series, users should also cite or reference the documentation for the source CDD and supply series when reproducibility details are relevant.

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
