# Open Bitcoin Metrics: Bitcoin Days Destroyed per Unit of Supply

This repository provides the following time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_cdd_per_supply_days_daily
```

The series reports daily Bitcoin Days Destroyed per unit of outstanding Bitcoin supply. It is computed from two already generated OBM series:

```text
obm_cdd_btcxdays_daily
obm_supply_btc_daily
```

The metric is a derived OBM series. It does not query Bitcoin Core directly. Instead, it reads the daily Bitcoin Days Destroyed series and the daily Bitcoin supply series, validates their structure and coverage, and computes a supply-normalized coin-age destruction measure.

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_cdd_per_supply_days_daily` |
| Display name | Bitcoin Days Destroyed per Unit of Supply |
| Unit | `days` |
| Frequency | `daily` |
| Time convention | UTC calendar day, inherited from the input OBM series |
| Source layer | Derived from existing OBM CSV files |
| External data required | No |
| Required OBM inputs | `obm_cdd_btcxdays_daily`, `obm_supply_btc_daily` |
| Main use | Supply-normalized coin-age destruction, dormant-supply activation, long-run comparability of CDD |

## Definition

Let \(CDD_d\) denote daily Bitcoin Days Destroyed on UTC calendar day \(d\), measured in BTC-days, and let \(S_d\) denote the outstanding Bitcoin supply on the same date, measured in BTC. The Bitcoin Days Destroyed per Unit of Supply series is defined as:

```text
CDDPerSupply_d = CDD_d / S_d
```

where:

```text
CDD_d = value of obm_cdd_btcxdays_daily on date d
S_d   = value of obm_supply_btc_daily on date d
```

The resulting unit is:

```text
BTC-days / BTC = days
```

If the supply value is zero, the output value is recorded as missing rather than zero, because the ratio is undefined.

## Interpretation

`obm_cdd_per_supply_days_daily` is a supply-normalized version of Bitcoin Days Destroyed. It measures how much coin age was destroyed on a given day per unit of outstanding Bitcoin supply.

The metric is useful for:

- comparing Bitcoin Days Destroyed across different monetary epochs;
- reducing the mechanical effect of Bitcoin's growing supply on raw CDD values;
- studying dormant-supply activation in supply-normalized terms;
- analyzing long-term holder behavior and older-coin movement;
- building econometric datasets where raw CDD may be difficult to compare over long historical periods;
- comparing OBM outputs with public supply-adjusted CDD indicators from external data providers.

For example, a value of:

```text
0.015
```

means that the daily Bitcoin Days Destroyed on that date was equivalent to 0.015 days per bitcoin outstanding.

The metric should not be interpreted as transaction volume, payment volume, exchange volume, user activity, or entity-adjusted settlement value. It is derived from raw Bitcoin Days Destroyed and supply. Therefore, it inherits the interpretation and limitations of the underlying CDD and supply series.

## Data format

The CSV file follows the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_cdd_per_supply_days_daily,0.012345678901,days,daily,OBM v0.1.0
2024-01-02,obm_cdd_per_supply_days_daily,0.009876543210,days,daily,OBM v0.1.0
```

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_cdd_per_supply_days_daily` |
| `value` | Daily Bitcoin Days Destroyed divided by outstanding Bitcoin supply |
| `unit` | Measurement unit: `days` |
| `frequency` | Observation frequency: `daily` |
| `release_version` | OBM dataset release version inferred from the input files |

Output values are written with 12 decimal places. Missing values are written as empty fields.

## Reproducibility

The metric is generated using a Python script that reads two existing OBM CSV files:

```text
obm_cdd_btcxdays_daily.csv
obm_supply_btc_daily.csv
```

The script performs the following steps:

1. reads the daily CDD input file;
2. reads the daily supply input file;
3. verifies that both files follow the standard OBM schema;
4. checks that the CDD file has series identifier `obm_cdd_btcxdays_daily`, unit `BTC-days`, and frequency `daily`;
5. checks that the supply file has series identifier `obm_supply_btc_daily`, unit `BTC`, and frequency `daily`;
6. rejects duplicate dates and missing numeric input values;
7. infers the overlapping date interval when `--start_date` or `--end_date` are omitted;
8. verifies complete daily coverage for the requested interval in both input files;
9. verifies that the input interval uses a single `release_version` value across both source series;
10. checks that CDD and supply values are non-negative;
11. computes `CDD_d / S_d` for each requested date;
12. records the value as missing when `S_d = 0`;
13. writes the resulting time series to a standard OBM CSV file;
14. optionally generates a plot of the computed series.

Because this is a derived metric, it does not require direct access to Bitcoin Core, JSON-RPC, transaction-output reconstruction, or external market data. Reproducibility depends on the two input OBM series and on the deterministic transformation documented above.

## Typical script usage

Generate the CSV file:

```bash
python3 compute_obm_cdd_per_supply_days_daily.py \
  data/daily/obm_cdd_btcxdays_daily.csv \
  data/daily/obm_supply_btc_daily.csv \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_cdd_per_supply_days_daily.csv
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_cdd_per_supply_days_daily.py \
  data/daily/obm_cdd_btcxdays_daily.csv \
  data/daily/obm_supply_btc_daily.csv \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_cdd_per_supply_days_daily.csv \
  --plot \
  --plot_output figures/obm_cdd_per_supply_days_daily.png
```

Both `--start_date` and `--end_date` are interpreted as UTC dates and are included in the output. If either date is omitted, the script uses the first or last date available in the common overlap of the two input files.

### Relevant optional parameters

| Parameter | Meaning | Default |
|---|---|---|
| `cdd_csv` | Positional argument. Input CSV file for `obm_cdd_btcxdays_daily` | required |
| `supply_csv` | Positional argument. Input CSV file for `obm_supply_btc_daily` | required |
| `--start_date` | Start date, inclusive, in `YYYY-MM-DD` format | first common date in the input files |
| `--end_date` | End date, inclusive, in `YYYY-MM-DD` format | last common date in the input files |
| `--output` | Output CSV file path | `obm_cdd_per_supply_days_daily.csv` |
| `--plot` | Generate a plot | disabled |
| `--plot_output` | Output path for the plot | same path as CSV, with `.png` extension |

The script does not expose a `--release_version` option. The output `release_version` is inferred from the two input files. If multiple release versions are found within the requested interval, the script stops and reports an error.

## Time needed for complete execution

This metric is computed from two existing OBM CSV files and does not scan the Bitcoin blockchain. As a result, execution is expected to be fast compared with full-node or spent-output-indexer metrics.

The exact execution time depends mainly on the length of the input files, disk speed, and whether plot generation is requested. A complete historical run should typically take seconds to a few minutes on ordinary desktop hardware, provided that the input CSV files are already available.

## Requirements

The generation script assumes:

- Python 3;
- two existing OBM input CSV files:
  - `obm_cdd_btcxdays_daily.csv`;
  - `obm_supply_btc_daily.csv`;
- both input files following the standard OBM schema;
- both input files using frequency `daily`;
- both input files having complete daily coverage over the requested interval;
- both input files using a single common `release_version` value across the requested interval;
- `matplotlib`, only if plot generation is requested.

This metric does not require a synchronized Bitcoin Core full node at execution time, Bitcoin Core JSON-RPC access, transaction-output reconstruction, address extraction, UTXO-set reconstruction, fee computation, or external price data.

## Validation

The script carries out the following validation checks during execution:

- verifies that each input CSV file contains the required standard OBM fields;
- verifies that the CDD input file uses series identifier `obm_cdd_btcxdays_daily`;
- verifies that the CDD input file uses unit `BTC-days`;
- verifies that the supply input file uses series identifier `obm_supply_btc_daily`;
- verifies that the supply input file uses unit `BTC`;
- verifies that both input files use frequency `daily`;
- rejects duplicate dates in either input file;
- rejects missing numeric input values;
- rejects invalid numeric input values;
- infers and validates the common overlapping date interval;
- verifies complete daily coverage in both input files for the requested interval;
- rejects negative CDD values;
- rejects negative supply values;
- records missing output values when supply is zero;
- verifies that the requested interval contains a single release version across both input files.

The following additional checks are recommended:

- verify that every requested date appears exactly once in the output file;
- confirm that all defined output values are non-negative;
- recompute selected dates manually as `CDD_d / S_d`;
- compare the output with the ratio obtained independently from the archived OBM input CSV files;
- inspect early Bitcoin dates where supply is zero or very small;
- compare selected periods with external supply-adjusted CDD indicators as a diagnostic check;
- inspect unusually large observations, since they may reflect genuine old-coin movement, data-boundary effects, or issues inherited from the source CDD series.

External comparisons should be interpreted cautiously because providers may differ in CDD definitions, timestamp conventions, supply definitions, entity-adjustment policies, smoothing choices, and treatment of early historical edge cases.

## Known limitations

Take into account that this metric:

- is a derived metric and inherits the limitations of `obm_cdd_btcxdays_daily` and `obm_supply_btc_daily`;
- depends on the UTC date convention used by the source OBM series;
- depends on the CDD convention used by OBM, including fractional-day accounting;
- depends on the supply convention used by OBM;
- is undefined when supply is zero;
- is not entity-adjusted and does not identify users, exchanges, custodians, self-transfers, change outputs, or changes of ownership;
- should not be interpreted as payment volume, exchange volume, or economically adjusted settlement value;
- may differ from public supply-adjusted CDD indicators because providers can use different CDD definitions, supply definitions, timestamp rules, smoothing conventions, or entity-adjustment heuristics.

Despite these facts, `obm_cdd_per_supply_days_daily` is a useful supply-normalized coin-age indicator. It is particularly valuable for comparing daily CDD across Bitcoin's monetary history, because it reduces the mechanical effect of the growing outstanding supply on raw Bitcoin Days Destroyed.

## Suggested citation

A formal citation will be added once the dataset receives a DOI.

For now, please cite this repository as:

```text
Llanos, D. R. Open Bitcoin Metrics: Reproducible Full-Node-Derived Bitcoin On-Chain Time Series.
Metric: Bitcoin Days Destroyed per Unit of Supply (obm_cdd_per_supply_days_daily).
GitHub repository, version OBM v0.1.0.
https://github.com/diegorllanos/open-bitcoin-metrics/
```

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
