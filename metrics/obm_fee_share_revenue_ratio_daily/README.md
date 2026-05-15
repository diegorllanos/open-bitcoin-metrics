# Open Bitcoin Metrics: Fees as Share of Miner Revenue

This repository provides the following derived time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_fee_share_revenue_ratio_daily
```

The series reports the share of BTC-denominated miner revenue accounted for by transaction fees. It is derived directly from two existing OBM series:

```text
obm_fees_btc_daily
obm_issuance_btc_daily
```

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_fee_share_revenue_ratio_daily` |
| Display name | Fees as share of miner revenue |
| Unit | `ratio` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Derived from `obm_fees_btc_daily` and `obm_issuance_btc_daily` |
| External data required | No |
| Main use | Fee substitution, security budget, subsidy-to-fee transition |

## Definition

Let `FeesBTC_d` denote the total transaction fees paid in BTC on UTC calendar day `d`, as reported by:

```text
obm_fees_btc_daily
```

Let `Issuance_d` denote the realized Bitcoin issuance on UTC calendar day `d`, as reported by:

```text
obm_issuance_btc_daily
```

Miner revenue in BTC is the sum of issuance and fees:

```text
MinerRevenueBTC_d = Issuance_d + FeesBTC_d
```

The fee share of miner revenue is defined as:

```text
FeeShare_d = FeesBTC_d / (Issuance_d + FeesBTC_d)
```

The metric is reported as a ratio, not as a percentage. For example:

```text
FeeShare_d = 0.025
```

means that transaction fees accounted for 2.5% of BTC-denominated miner revenue on that date.

## Treatment of zero-denominator dates

On dates where:

```text
Issuance_d + FeesBTC_d = 0
```

the fee-share ratio is undefined. This can occur in the first days of Bitcoin history under the UTC timestamp convention, when no blocks, no issuance, and no fees are assigned to a particular calendar day.

OBM records such values as missing, using an empty `value` field in the CSV file:

```csv
date,series_id,value,unit,frequency,release_version
2009-01-01,obm_fee_share_revenue_ratio_daily,,ratio,daily,OBM v0.1.0
```

This convention is deliberate. A missing value is preferable to zero, because zero would mean that fees represented 0% of positive miner revenue. In zero-denominator cases, there is no miner revenue from which a share can be computed.

## Interpretation

`obm_fee_share_revenue_ratio_daily` measures the fraction of BTC-denominated miner compensation that comes from transaction fees rather than newly issued BTC.

This metric is useful for:

- studying the transition from subsidy-dominated to fee-supported miner compensation;
- analyzing Bitcoin's long-run security budget;
- comparing fee-market development across subsidy eras;
- evaluating the economic significance of transaction fees around congestion episodes;
- measuring the relative role of fees after halving events;
- building econometric or descriptive datasets related to miner incentives.

The series should be interpreted as a relative BTC-denominated revenue composition metric. It does not measure total miner revenue, miner profit, mining costs, fiat-denominated revenue, or miner margins.

## Relationship with source series

This metric is a direct transformation of:

```text
obm_fees_btc_daily
obm_issuance_btc_daily
```

The source metric `obm_fees_btc_daily` reports the daily amount of BTC paid by users as transaction fees. The source metric `obm_issuance_btc_daily` reports the daily amount of newly issued BTC.

The fee-share ratio combines both series as follows:

```text
obm_fee_share_revenue_ratio_daily =
    obm_fees_btc_daily /
    (obm_issuance_btc_daily + obm_fees_btc_daily)
```

The denominator is equivalent to BTC-denominated miner revenue:

```text
obm_miner_revenue_btc_daily =
    obm_issuance_btc_daily + obm_fees_btc_daily
```

Therefore, when `obm_miner_revenue_btc_daily` is also available, the following equivalent expression can be used as a validation check:

```text
obm_fee_share_revenue_ratio_daily =
    obm_fees_btc_daily / obm_miner_revenue_btc_daily
```

The script computes the ratio from issuance and fees directly, rather than querying the Bitcoin blockchain again.

## Data format

The CSV file follows the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_fee_share_revenue_ratio_daily,0.007216384512,ratio,daily,OBM v0.1.0
2024-01-02,obm_fee_share_revenue_ratio_daily,0.008553291047,ratio,daily,OBM v0.1.0
```
## Precision

For dates with positive BTC-denominated miner revenue, the script writes the `value` 
field with twelve decimal places:

```text
value = obm_fees_btc_daily / (obm_issuance_btc_daily + obm_fees_btc_daily)
```
Undefined values caused by `issuance + fees = 0` are written as an empty `value` field.

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_fee_share_revenue_ratio_daily` |
| `value` | Fees divided by issuance plus fees; empty when undefined |
| `unit` | Measurement unit: `ratio` |
| `frequency` | Observation frequency: `daily` |
| `release_version` | OBM dataset release version inherited from the source interval |

## Reproducibility

The metric is generated using a Python script that reads the already generated OBM daily issuance and daily fees CSV files.

For each date in the requested interval, the script:

1. reads the input file `obm_issuance_btc_daily.csv`;
2. reads the input file `obm_fees_btc_daily.csv`;
3. verifies that both input files follow the standard OBM schema;
4. checks that the input series identifiers are `obm_issuance_btc_daily` and `obm_fees_btc_daily`;
5. checks that both source series use unit `BTC` and frequency `daily`;
6. determines the requested date interval, or the common overlapping interval if dates are not explicitly provided;
7. verifies that both input files contain one row for every date in the selected interval;
8. computes `fees / (issuance + fees)` for each date with a positive denominator;
9. records a missing value when `issuance + fees = 0`;
10. writes the resulting ratio series to CSV.

Unlike `obm_fees_btc_daily` and `obm_issuance_btc_daily`, this script does not query Bitcoin Core. It is a deterministic transformation of already generated OBM time series.

## Typical script usage

Generate the CSV file:

```bash
python3 compute_obm_fee_share_revenue_ratio_daily.py \
  data/daily/obm_issuance_btc_daily.csv \
  data/daily/obm_fees_btc_daily.csv \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_fee_share_revenue_ratio_daily.csv
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_fee_share_revenue_ratio_daily.py \
  data/daily/obm_issuance_btc_daily.csv \
  data/daily/obm_fees_btc_daily.csv \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_fee_share_revenue_ratio_daily.csv \
  --plot \
  --plot_output figures/obm_fee_share_revenue_ratio_daily.png
```

If `--start_date` and `--end_date` are omitted, the script uses the common overlapping date range covered by both input files.

## Requirements

The generation script assumes:

- an existing OBM-compatible `obm_issuance_btc_daily.csv` file;
- an existing OBM-compatible `obm_fees_btc_daily.csv` file;
- Python 3;
- `matplotlib`, only if plot generation is requested.

This derived metric does not require:

- a running Bitcoin Core node;
- access to the Bitcoin Core JSON-RPC interface;
- transaction-level data;
- previous-output reconstruction;
- fee reconstruction;
- external price data;
- third-party APIs.

## Validation

The following internal checks are recommended:

- verify that every requested date appears exactly once in the output;
- verify that every requested date exists in both input files;
- check that source values are non-negative BTC amounts;
- check that all defined ratio values lie between 0 and 1;
- verify that missing values occur only when `issuance + fees = 0`;
- confirm that the source interval uses a single `release_version`;
- compare the denominator `issuance + fees` with `obm_miner_revenue_btc_daily` when that series is available.

The most important consistency condition is:

```text
FeeShare_d = FeesBTC_d / (Issuance_d + FeesBTC_d)
```

for all dates where:

```text
Issuance_d + FeesBTC_d > 0
```

A secondary validation identity, when miner revenue is available, is:

```text
FeeShare_d = FeesBTC_d / MinerRevenueBTC_d
```
## Aggregation to lower frequencies

If this metric is aggregated to monthly frequency, monthly values should not be computed 
mechanically as arithmetic averages of daily ratios without explicit justification. A more 
interpretable monthly value is obtained by first summing monthly fees and monthly issuance 
and then computing:

```text
FeeShare_m = FeesBTC_m / (Issuance_m + FeesBTC_m)
```

where `FeesBTC_m` and `Issuance_m` are the monthly sums of the daily source series. This preserves 
the interpretation of the metric as the fee share of total BTC-denominated miner revenue over 
the month.

## Known limitations

It is important to remember that this metric:

- is a derived series, not an independent full-node reconstruction;
- depends entirely on the quality and completeness of `obm_issuance_btc_daily` and `obm_fees_btc_daily`;
- is undefined when `issuance + fees = 0`;
- reports a ratio, not a percentage;
- measures the BTC-denominated composition of miner revenue, not fiat-denominated revenue;
- does not measure miner profit, mining costs, energy costs, hardware costs, or operating margins;
- inherits the timestamp conventions, definitions, and release versions of the source series;
- may change if either source series is revised in a later OBM release.

Despite these limitations, `obm_fee_share_revenue_ratio_daily` is a useful derived OBM series. It provides a transparent measure of the relative importance of transaction fees in miner compensation and supports research on Bitcoin's security budget, fee-market development, halving dynamics, and the long-run transition from subsidy-based to fee-supported miner revenue.

## Suggested citation

A formal citation will be added once the dataset receives a DOI.

For now, please cite this repository as:

```text
Llanos, D. R. Open Bitcoin Metrics: Reproducible Full-Node-Derived Bitcoin On-Chain Time Series
Metric: Fees as Share of Miner Revenue (obm_fee_share_revenue_ratio_daily).
GitHub repository, version OBM v0.1.0.
https://github.com/diegorllanos/open-bitcoin-metrics/
```

Because this metric is derived from `obm_issuance_btc_daily` and `obm_fees_btc_daily`, users should also cite those source series when this fee-share metric is used.

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
