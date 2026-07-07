# Open Bitcoin Metrics: Bitcoin Supply

This repository provides the following derived time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_supply_btc_daily
```

The series reports Bitcoin supply, measured in BTC, computed as the cumulative sum of realized daily issuance 
from `2009-01-01` through each reported date.  It is derived directly from the 
OBM daily realized issuance series:

```text
obm_issuance_btc_daily
```

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_supply_btc_daily` |
| Display name | Accumulated Bitcoin supply |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Derived from `obm_issuance_btc_daily` |
| External data required | No |
| Main use | Period issuance, cumulative monetary flow, supply-growth analysis |

## Definition

Let `Issuance_d` denote the realized Bitcoin issuance on UTC calendar day `d`, as reported by:

```text
obm_issuance_btc_daily
```

For a selected date interval from `s=2009-01-01` to `e`, both inclusive, accumulated supply at date `d` is defined as:

```text
AccumIssuance_d = sum_{k=s}^{d} Issuance_k
```

for every date `d` such that:

```text
s <= d <= e
```

The cumulative value is reset at 2009-01-01. Therefore, the value on the first date of the interval equals 
the daily issuance on that date:

```text
AccumIssuance_s = Issuance_s
```

This metric is therefore a cumulative Bitcoin supply since the Bitcoin genesis block.

## Interpretation

`obm_supply_btc_daily` measures how much new Bitcoin has been issued cumulatively since the Bitcoin genesis block, inclusive.

This metric is useful for:

- measuring total realized issuance up to a certain date
- studying cumulative supply growth; 
- analyzing issuance before and after halving events;
- comparing monetary expansion across subperiods;
- building econometric or descriptive datasets where cumulative issuance is required;
- deriving interval-specific supply-flow variables.

The series should be interpreted as a cumulative transformation of daily realized issuance. It does not independently reconstruct block-level issuance. Its accuracy depends on the accuracy and completeness of the source series `obm_issuance_btc_daily`.

## Relationship with `obm_issuance_btc_daily`

This metric is a direct accumulation of `obm_issuance_btc_daily`.

The source metric reports the daily flow of newly issued BTC:

```text
obm_issuance_btc_daily
```

The accumulated metric reports the running sum of those daily flows from 2009-01-01:

```text
obm_supply_btc_daily
```

The accumulated series is therefore best understood as a derived convenience metric. It makes explicit a transformation that researchers often apply manually when computing period issuance.

## Data format

The CSV file follows the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_supply_btc_daily,19587102.29497096,BTC,daily,OBM v0.1.0
2024-01-02,obm_supply_btc_daily,19587921.04497096,BTC,daily,OBM v0.1.0
```

## Precision

The script writes the `value` field with eight decimal places:

```text
value = cumulative sum of obm_issuance_btc_daily from 2009-01-01
```

This matches the BTC-denominated precision convention used by other OBM series.

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_supply_btc_daily` |
| `value` | Accumulated Bitcoin issuance from the selected start date |
| `unit` | Measurement unit: `BTC` |
| `frequency` | Observation frequency: `daily` |
| `release_version` | OBM dataset release version inherited from the source interval |

## Reproducibility

The metric is generated using a Python script that reads the already generated OBM daily issuance CSV file.

For each date in the requested interval, the script:

1. reads the input file `obm_issuance_btc_daily.csv`;
2. verifies that the input file follows the standard OBM schema;
3. checks that the input series identifier is `obm_issuance_btc_daily`;
4. checks that the unit is `BTC` and the frequency is `daily`;
5. filters the observations between the requested starting and ending dates, both inclusive;
6. verifies that no required daily observation is missing;
7. computes the running cumulative sum of daily issuance values;
8. writes the resulting accumulated series to CSV.

Unlike `obm_issuance_btc_daily`, this script does not query Bitcoin Core and does not reconstruct coinbase outputs or transaction fees. It is a deterministic transformation of the daily issuance file.

## Typical script usage

Generate the CSV file:

```bash
python3 compute_obm_supply_btc_daily.py \
  data/daily/obm_issuance_btc_daily.csv \
  --end_date 2024-01-31 \
  --output data/daily/obm_supply_btc_daily.csv
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_supply_btc_daily.py \
  data/daily/obm_issuance_btc_daily.csv \
  --end_date 2024-01-31 \
  --output data/daily/obm_supply_btc_daily.csv \
  --plot \
  --plot_output figures/obm_supply_btc_daily.png
```

## Requirements

The generation script assumes:

- an existing OBM-compatible `obm_issuance_btc_daily.csv` file;
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
- verify that every requested date exists in the input `obm_issuance_btc_daily.csv`;
- check that output values are non-negative BTC amounts;
- check that the accumulated series is monotonically non-decreasing;
- verify that first differences of `obm_supply_btc_daily` equal the corresponding values of `obm_issuance_btc_daily`;
- confirm that the source interval uses a single `release_version`.

The most important consistency condition is:

```text
AccumIssuance_d - AccumIssuance_{d-1} = Issuance_d
```

for all dates after the selected starting date.

## Known limitations

It is important to remember that this metric:

- is a derived series, not an independent full-node reconstruction;
- depends entirely on the quality and completeness of `obm_issuance_btc_daily`;
- resets its cumulative value at 2009-01-01.
- represents total cumulative Bitcoin supply, because the start date corresponds to the beginning of the issuance history;
- inherits the timestamp convention, issuance definition, and release version of the source daily issuance series;
- may change if the underlying daily issuance series is revised in a later OBM release.

Despite these limitations, `obm_supply_btc_daily` is a useful derived OBM series. It provides a convenient measure of cumulative realized issuance over arbitrary research intervals and supports monetary-supply, halving-period, and supply-growth analysis.

## Suggested citation

```text
Llanos, D. R. Open Bitcoin Metrics: Verifiable Full-Node-Derived Bitcoin Time Series for Economic Research
Metric: Bitcoin Supply (obm_supply_btc_daily).
ArXiv preprint, https://arxiv.org/abs/2607.03124
```

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
