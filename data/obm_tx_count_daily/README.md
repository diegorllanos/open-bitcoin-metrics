# Open Bitcoin Metrics: Daily Transaction Count

This repository provides the first time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_tx_count_daily
```

The series reports the daily number of Bitcoin transactions confirmed on-chain, computed directly from a running Bitcoin Core full node.

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_tx_count_daily` |
| Display name | Daily Bitcoin transaction count |
| Unit | `transactions` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Bitcoin Core full node |
| External data required | No |
| Main use | Network activity, transaction demand, settlement activity |

## Definition

Let \(B_d\) denote the set of Bitcoin blocks assigned to UTC calendar day \(d\), and let \(N_b\) denote the number of transactions included in block \(b\). The daily transaction count is defined as:

```text
TxCount_d = sum_{b in B_d} N_b
```

A block is assigned to a day according to the UTC date derived from the block timestamp returned by Bitcoin Core.

Coinbase transactions are included because they are valid transactions contained in blocks and are part of the block-level transaction count.

## Interpretation

`obm_tx_count_daily` is a basic indicator of Bitcoin on-chain activity. It measures the number of confirmed transactions per UTC day.

This metric is useful for:

- studying Bitcoin network usage;
- measuring transaction demand;
- comparing activity across different market periods;
- combining with fees, block weight, miner revenue, or coin-age metrics;
- building econometric datasets for Bitcoin research.

However, the series should not be interpreted as a direct count of users, payments, or economically distinct transfers. A Bitcoin transaction may include multiple inputs and outputs, represent batching, self-transfer activity, exchange activity, or custodial operations. Conversely, many economic transfers can occur off-chain and therefore do not appear as separate Bitcoin transactions.

## Data format

The CSV file follows the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_tx_count_daily,731566,transactions,daily,OBM v0.1.0
2024-01-02,obm_tx_count_daily,649123,transactions,daily,OBM v0.1.0
```

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_tx_count_daily` |
| `value` | Number of confirmed Bitcoin transactions |
| `unit` | Measurement unit: `transactions` |
| `frequency` | Observation frequency: `daily` |
| `release_version` | OBM dataset release version |

## Reproducibility

The metric is generated using a Python script that queries a local Bitcoin Core node through JSON-RPC.
You can find the script in the "scripts" directory of this repository.

For each block in the requested date interval, the script:

1. obtains the block hash from the block height;
2. retrieves the decoded block object from Bitcoin Core;
3. reads the number of transactions in the block;
4. assigns the block to a UTC calendar day using the block timestamp;
5. aggregates transaction counts by day;
6. writes the resulting time series to CSV.

The script uses a safety height margin around the estimated date interval because Bitcoin block timestamps are not strictly monotonic in block height. This reduces the risk of missing blocks near daily boundaries.

## Typical script usage

Generate the CSV file:

```bash
python3 compute_obm_tx_count_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_tx_count_daily.csv \
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_tx_count_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_tx_count_daily.csv \
  --plot \
  --plot_output figures/obm_tx_count_daily.png
```

## Requirements

The generation script assumes:

- a synchronized Bitcoin Core full node;
- access to the Bitcoin Core JSON-RPC interface;
- Python 3;
- `matplotlib`, only if plot generation is requested.

This metric does not require transaction-output reconstruction, address extraction, UTXO-set reconstruction, or external price data.

## Validation

The following internal checks are recommended:

- verify that every requested date appears exactly once;
- check that values are non-negative integers;
- compare daily totals with independent block-level aggregation;
- confirm that the scanned block-height range covers the requested dates;
- compare selected periods with external public Bitcoin data providers as a diagnostic check.

External comparisons should be interpreted cautiously because providers may use different timestamp conventions, reorganization policies, or transaction-count definitions.

## Known limitations

This metric has several limitations:

- it counts transactions, not users;
- it does not identify economically distinct payments;
- it does not adjust for batching;
- it does not remove self-transfers or exchange internal activity;
- it does not measure transaction value;
- it depends on the block timestamp convention used to assign blocks to calendar days.

Despite these limitations, `obm_tx_count_daily` is a useful baseline indicator of Bitcoin on-chain activity and a natural starting point for the Open Bitcoin Metrics dataset.

## Suggested citation

A formal citation will be added once the dataset receives a DOI.

For now, please cite this repository as:

```text
Llanos, D. R. Open Bitcoin Metrics: Reproducible Full-Node-Derived Bitcoin On-Chain Time Series
Metric: Daily Bitcoin Transaction Count (obm_tx_count_daily).
GitHub repository, version OBM v0.1.0.
https://github.com/diegorllanos/open-bitcoin-metrics/
```

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
