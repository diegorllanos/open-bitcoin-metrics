# Open Bitcoin Metrics: Daily Coin Days Destroyed

This repository provides the following time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_cdd_btcxdays_daily
```

The series reports daily **Coin Days Destroyed** for Bitcoin, computed directly from a running Bitcoin Core full node.

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_cdd_btcxdays_daily` |
| Display name | Daily Coin Days Destroyed |
| Unit | `BTC-days` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Bitcoin Core full node |
| External data required | No |
| Main use | Long-term holder activity, coin-age dynamics, dormancy analysis |

## Definition

Let \(S_d\) denote the set of Bitcoin transaction outputs spent in blocks assigned to UTC calendar day \(d\). For each spent output \(i\), let \(v_i\) denote its value in BTC, let \(t_i^{created}\) denote the timestamp of the block in which the output was created, and let \(t_i^{spent}\) denote the timestamp of the block in which the output was spent.

The age of the spent output, measured in days, is defined as:

```text
age_i = max(0, (t_i_spent - t_i_created) / 86400)
```

The contribution of that spent output to Coin Days Destroyed is:

```text
CDD_i = value_i_BTC * age_i
```

The daily Coin Days Destroyed series is then:

```text
CDD_d = sum_{i in S_d} CDD_i
```

A block is assigned to a day according to the UTC date derived from the block timestamp returned by Bitcoin Core.

The unit is `BTC-days`, because the metric multiplies a Bitcoin-denominated value by the number of days that value remained unspent.

## Interpretation

`obm_cdd_btcxdays_daily` is a raw spent-output coin-age metric. It gives more weight to the movement of older coins than to the movement of recently active coins.

For example:

```text
1 BTC moved after 1 day     = 1 BTC-day
1 BTC moved after 100 days  = 100 BTC-days
10 BTC moved after 100 days = 1,000 BTC-days
```

This metric is useful for:

- studying long-term holder activity;
- detecting movements of older or dormant coins;
- distinguishing recent transaction churn from the movement of aged supply;
- constructing dormancy and coin-age indicators;
- comparing network activity with transaction count, fees, supply, and market variables;
- building econometric datasets for Bitcoin research.

The series should not be interpreted as a direct measure of transaction demand or payment volume. It is a measure of destroyed coin age. A large value can occur because many coins moved, because very old coins moved, or both.

## Data format

The CSV file follows the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_cdd_btcxdays_daily,123456789.12345678,BTC-days,daily,OBM v0.1.0
2024-01-02,obm_cdd_btcxdays_daily,98765432.87654321,BTC-days,daily,OBM v0.1.0
```

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_cdd_btcxdays_daily` |
| `value` | Daily Coin Days Destroyed |
| `unit` | Measurement unit: `BTC-days` |
| `frequency` | Observation frequency: `daily` |
| `release_version` | OBM dataset release version |

## Reproducibility

The metric is generated using a Python script that queries a local Bitcoin Core node through JSON-RPC.
You can find the script in the "scripts" directory of this repository.

Unlike simple block-level metrics, Coin Days Destroyed requires knowledge of the value and creation time of every spent output. For that reason, the script maintains a persistent SQLite state database that reconstructs and stores the currently unspent output set needed for future incremental updates.

For each block processed, the script:

1. obtains the block hash from the block height;
2. retrieves the decoded block object from Bitcoin Core;
3. reads the block timestamp;
4. assigns the block to a UTC calendar day using that timestamp;
5. for each non-coinbase transaction input, retrieves the corresponding previous output from the local state database;
6. computes the age of the spent output using the creation and spending block timestamps;
7. multiplies the spent output value by its age in days;
8. adds the resulting BTC-days to the daily total;
9. deletes the spent output from the local state database;
10. inserts all newly created outputs into the local state database;
11. writes the resulting time series to CSV.

The persistent state database allows the script to run incrementally. The first run reconstructs the historical state from genesis. Later runs resume from the last processed block and only process new blocks.

The script uses a safety height margin around the estimated date interval because Bitcoin block timestamps are not strictly monotonic in block height. This reduces the risk of missing blocks near daily boundaries.

## Typical script usage

Initial historical reconstruction:

```bash
python3 compute_obm_cdd_btcxdays_daily.py \
  --start_date 2009-01-03 \
  --end_date 2024-01-31 \
  --output data/daily/obm_cdd_btcxdays_daily.csv \
  --state_db cache/obm_cdd_btcxdays_state.sqlite \
  --reset_state_db
```

Incremental update:

```bash
python3 compute_obm_cdd_btcxdays_daily.py \
  --start_date 2009-01-03 \
  --end_date 2024-02-01 \
  --output data/daily/obm_cdd_btcxdays_daily.csv \
  --state_db cache/obm_cdd_btcxdays_state.sqlite
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_cdd_btcxdays_daily.py \
  --start_date 2009-01-03 \
  --end_date 2024-02-01 \
  --output data/daily/obm_cdd_btcxdays_daily.csv \
  --state_db cache/obm_cdd_btcxdays_state.sqlite \
  --plot \
  --plot_output figures/obm_cdd_btcxdays_daily.png
```

For daily automated execution, a conservative pattern is to use yesterday in UTC as the end date and to avoid processing the most recent blocks:

```bash
python3 compute_obm_cdd_btcxdays_daily.py \
  --start_date 2009-01-03 \
  --end_date "$(date -u -d yesterday +\%F)" \
  --output data/daily/obm_cdd_btcxdays_daily.csv \
  --state_db cache/obm_cdd_btcxdays_state.sqlite \
  --min_confirmations 100
```

## Requirements

The generation script assumes:

- a synchronized Bitcoin Core full node;
- access to the Bitcoin Core JSON-RPC interface;
- Python 3;
- SQLite, available through Python's standard library;
- `matplotlib`, only if plot generation is requested.

This metric does not require external price data, address extraction, user/entity clustering, or third-party APIs. However, it requires access to historical blocks so that the script can reconstruct previous outputs and their creation times.

A non-pruned Bitcoin Core node is strongly recommended.

## Persistent state database

The script uses a local SQLite database to make daily updates feasible. The database stores:

- the current outpoint set;
- daily CDD values already computed;
- processed block metadata;
- processing metadata.

The state database is part of the reproducible computation of this metric. If the metric definition changes, or if a chain reorganization is detected beyond the script's simple consistency checks, the database should be rebuilt with:

```bash
--reset_state_db
```

The script follows a simple and safe reorganization policy. On each run, it compares the last processed block hash stored in the SQLite database with the block hash currently reported by Bitcoin Core at the same height. If they differ, the script aborts rather than attempting an automatic rollback.

## Comparison with Coin Metrics `TxTfrValDayDst`

Users familiar with Coin Metrics may compare `obm_cdd_btcxdays_daily` with the Coin Metrics metric `TxTfrValDayDst`, commonly described as transferred days destroyed.

The two series are related, but they should not be expected to match exactly.

`obm_cdd_btcxdays_daily` is defined as a transparent **raw spent-output** metric:

```text
For each spent output:
    CDD = previous_output_value_BTC * age_in_days
```

The value and age are reconstructed directly from Bitcoin full-node data. The metric is then aggregated by the UTC date of the block in which the output is spent.

By contrast, Coin Metrics' `TxTfrValDayDst` belongs to their transfer-value metric family. It may therefore reflect provider-specific transfer semantics, daily interval conventions, and historical edge-case handling that are not identical to raw spent-output accounting.

In early Bitcoin data, especially January 2009, differences can be noticeable. Probable reasons include:

- **Transfer-level versus spent-output-level accounting.** OBM counts destroyed coin age from spent previous outputs. Coin Metrics' metric name and documentation refer to transferred value, which may imply a different abstraction from raw spent inputs.
- **Treatment of early coinbase-origin outputs.** The first non-coinbase transactions spend coins originally created in coinbase transactions. Provider-specific conventions for when coinbase-origin coins begin accumulating age may affect the earliest observations.
- **Daily interval labeling or boundary conventions.** Early blocks and transactions near UTC boundaries may be assigned differently depending on whether the provider labels intervals by start time, end time, or another internal convention.
- **Block timestamp conventions.** OBM uses the block timestamp returned by Bitcoin Core for both creation and spending time. Alternative conventions can shift or slightly rescale early observations.
- **Early-sample sensitivity.** During January 2009, there are very few non-coinbase transactions. A single definitional difference can dominate the daily value.

For these reasons, OBM does not claim that `obm_cdd_btcxdays_daily` is a replica of Coin Metrics' `TxTfrValDayDst`. Instead, OBM prioritizes a transparent and reproducible definition that can be audited from a Bitcoin Core full node.

When validating against Coin Metrics, it is advisable to report both:

- comparison over the full available sample;
- comparison after excluding the earliest Bitcoin period, such as the first 30 or 90 days.

The latter comparison is likely to be more informative about the general behavior of the series, while the former is useful for documenting early-chain definitional differences.

## Validation

The following internal checks are recommended:

- verify that every requested date appears exactly once;
- check that values are non-negative;
- confirm that the scanned block-height range covers the requested dates;
- verify that the persistent state database resumes from the expected block height;
- check that the last processed block hash matches the current Bitcoin Core chain;
- inspect the number of negative apparent output ages floored to zero;
- compare selected periods with independently computed CDD-like metrics as a diagnostic check.

External comparisons should be interpreted cautiously because data providers may use different timestamp conventions, transfer definitions, coinbase-origin conventions, or daily-boundary rules.

## Known limitations

Take into account that this metric:

- is a raw spent-output metric, not a provider-specific transfer-value metric;
- depends on the block timestamp convention used to compute output age and daily assignment;
- may differ from commercial CDD-like metrics such as Coin Metrics' `TxTfrValDayDst`;
- is especially sensitive to definitional choices in the earliest Bitcoin period;
- does not adjust for self-transfers, change outputs, custodial activity, or exchange operations;
- requires a persistent local state database for efficient incremental updates.
- carries out a reconstruction which explicitly handles the two historical duplicate coinbase 
transaction pairs that existed before BIP30 enforcement by overwriting the earlier txid:vout entry 
in the local outpoint state and recording the event in metadata.

Said that, `obm_cdd_btcxdays_daily` is a useful baseline coin-age metric which provides a transparent measure of destroyed coin age and is valuable for studying long-term holder behavior, dormant-supply movement, dormancy, and the relationship between on-chain activity and market conditions.

## Suggested citation

A formal citation will be added once the dataset receives a DOI.

For now, please cite this repository as:

```text
Llanos, D. R. Open Bitcoin Metrics: Reproducible Full-Node-Derived Bitcoin On-Chain Time Series
Metric: Daily Coin Days Destroyed (obm_cdd_btcxdays_daily).
GitHub repository, version OBM v0.1.0.
https://github.com/diegorllanos/open-bitcoin-metrics/
```

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
