# Open Bitcoin Metrics: Daily Transaction Fees in BTC

This repository provides the following time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_fees_btc_daily
```

The series reports daily Bitcoin transaction fees, measured in BTC, computed directly from a running Bitcoin Core full node.

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_fees_btc_daily` |
| Display name | Daily transaction fees in BTC |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Bitcoin Core full node |
| External data required | No |
| Main use | Fee market, block-space demand, miner incentives, security-budget analysis |

## Definition

Let `B_d` denote the set of Bitcoin blocks assigned to UTC calendar day `d`. For each non-coinbase transaction `j` included in block `b`, the transaction fee is defined as:

```text
Fee_j = sum(input values) - sum(output values)
```

Daily transaction fees in BTC are defined as:

```text
FeesBTC_d = sum of Fee_j over all non-coinbase transactions
            included in blocks assigned to day d
```

A block is assigned to a day according to the UTC date derived from the block timestamp returned by Bitcoin Core.

Coinbase transactions are excluded from transaction-level fee computation because they do not spend ordinary previous outputs. Instead, the coinbase transaction collects the block subsidy and transaction fees.

This metric is different from `obm_miner_revenue_btc_daily`. Daily transaction fees measure only BTC paid by users to miners through transaction fees. Miner revenue includes both fees and newly issued BTC:

```text
Miner revenue in BTC = issuance + transaction fees
```

## Interpretation

`obm_fees_btc_daily` measures the BTC-denominated transaction fees paid by Bitcoin users for transactions confirmed in blocks assigned to each UTC calendar day.

This metric is useful for:

- studying Bitcoin's fee market;
- measuring demand for block space;
- analyzing congestion episodes;
- studying miner incentives;
- evaluating the transition from subsidy-based to fee-supported miner compensation;
- constructing security-budget indicators;
- building econometric datasets for Bitcoin research.

The series should be interpreted as fees measured in BTC, not in fiat currency. It does not account for the market price of Bitcoin. To obtain fiat-denominated transaction fees, this series would need to be combined with an external BTC/USD price series. Such a derived metric would no longer be purely full-node-derived.

## Data format

The CSV file follows the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_fees_btc_daily,6.68123456,BTC,daily,OBM v0.1.0
2024-01-02,obm_fees_btc_daily,7.67187654,BTC,daily,OBM v0.1.0
```

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_fees_btc_daily` |
| `value` | Total transaction fees assigned to the UTC date |
| `unit` | Measurement unit: `BTC` |
| `frequency` | Observation frequency: `daily` |
| `release_version` | OBM dataset release version |

## Reproducibility

The metric is generated using a Python script that queries a local Bitcoin Core node through JSON-RPC.
You can find the script in the "scripts" directory of this repository.

For each block in the requested date interval, the script:

1. obtains the block hash from the block height;
2. retrieves the decoded block object from Bitcoin Core;
3. reads the block timestamp;
4. assigns the block to a UTC calendar day using that timestamp;
5. skips the coinbase transaction;
6. computes the fee of each non-coinbase transaction;
7. sums transaction fees over the block;
8. adds the resulting BTC amount to the daily transaction-fee total;
9. writes the resulting time series to CSV.

For a non-coinbase transaction, the script uses the fee field if Bitcoin Core provides it. Otherwise, it reconstructs the fee as the difference between the total value of the transaction inputs and the total value of the transaction outputs. This reconstruction requires previous-output values.

The script uses a safety height margin around the estimated date interval because Bitcoin block timestamps are not strictly monotonic in block height. This reduces the risk of missing blocks near daily boundaries.

## Typical script usage

Generate the CSV file:

```bash
python3 compute_obm_fees_btc_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_fees_btc_daily.csv
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_fees_btc_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_fees_btc_daily.csv \
  --plot \
  --plot_output figures/obm_fees_btc_daily.png
```

## Time needed for complete execution

For reference, execution time should be similar to other block-scanning scripts that retrieve decoded blocks with transaction-level information. It is expected to be slower than `obm_block_count_daily`, because the script must retrieve decoded transaction data and fee information, but it does not require maintaining a persistent local outpoint database as in Bitcoin Days Destroyed.

A precise execution-time benchmark should be added after a complete historical run on the reference OBM machine.

## Requirements

The generation script assumes:

- a synchronized Bitcoin Core full node;
- access to the Bitcoin Core JSON-RPC interface;
- Python 3;
- `matplotlib`, only if plot generation is requested.

This metric does not require address extraction, user/entity clustering, external price data, or third-party APIs.

It does require transaction-level fee information. The script is designed to retrieve decoded block data with previous-output information when needed. A non-pruned Bitcoin Core node is strongly recommended for historical reconstruction, because previous-output values may require access to historical block and undo data.

## Validation

The following internal checks are recommended:

- verify that every requested date appears exactly once;
- check that values are non-negative BTC amounts;
- confirm that the scanned block-height range covers the requested dates;
- verify that each processed block contains a non-empty transaction list;
- verify that coinbase transactions are excluded from transaction-level fee computation;
- check that no non-coinbase transaction has a negative computed fee;
- compare daily fees with the difference between miner revenue and issuance once both series are available;
- inspect days with unusually high fees, since they may reflect fee-market congestion, unusual transactions, or data-extraction issues.

The most important consistency relation is:

```text
obm_fees_btc_daily =
    obm_miner_revenue_btc_daily - obm_issuance_btc_daily
```

up to any differences caused by timestamp conventions, implementation bugs, or later revisions.

External comparisons should be interpreted cautiously because providers may differ in timestamp conventions, reorganization policies, historical edge-case handling, or daily-boundary rules.

## Known limitations

Take into account that this metric:

- measures transaction fees in BTC, not in USD or any other fiat currency;
- excludes the block subsidy;
- is not the same as miner revenue, because miner revenue includes both issuance and fees;
- depends on accurate transaction fee reconstruction;
- may require previous-output information for historical transactions;
- may require a non-pruned node with sufficient historical data;
- depends on the block timestamp convention used to assign blocks to calendar days;
- may vary from day to day because of fee-market conditions, congestion, transaction demand, and the number of blocks assigned to each UTC day.

Despite these facts, `obm_fees_btc_daily` is a central OBM series. It provides a transparent measure of BTC-denominated transaction fees and is useful for studying Bitcoin's fee market, block-space demand, miner incentives, the security budget, and the long-run transition from subsidy-based to fee-supported miner compensation.

## Suggested citation

A formal citation will be added once the dataset receives a DOI.

For now, please cite this repository as:

```text
Llanos, D. R. Open Bitcoin Metrics: Reproducible Full-Node-Derived Bitcoin On-Chain Time Series
Metric: Daily Transaction Fees in BTC (obm_fees_btc_daily).
GitHub repository, version OBM v0.1.0.
https://github.com/diegorllanos/open-bitcoin-metrics/
```

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
