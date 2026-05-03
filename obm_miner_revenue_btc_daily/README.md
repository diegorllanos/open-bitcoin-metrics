# Open Bitcoin Metrics: Daily Miner Revenue in BTC

This repository provides the following time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_miner_revenue_btc_daily
```

The series reports daily Bitcoin miner revenue, measured in BTC, computed directly from a running Bitcoin Core full node.

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_miner_revenue_btc_daily` |
| Display name | Daily miner revenue in BTC |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Bitcoin Core full node |
| External data required | No |
| Main use | Miner incentives, security budget, subsidy and fee analysis |

## Definition

Let B_d denote the set of Bitcoin blocks assigned to UTC calendar day d. For each block b, let C_b denote the total output value of the coinbase transaction in that block, measured in BTC.

Daily miner revenue in BTC is defined as:

```text
MinerRevenueBTC_d = sum_{b in B_d} C_b
```

A block is assigned to a day according to the UTC date derived from the block timestamp returned by Bitcoin Core.

In Bitcoin, the coinbase transaction pays the miner both newly issued BTC and transaction fees. Therefore:

```text
Miner revenue in BTC = issuance + transaction fees
```

Equivalently, for each block:

```text
MinerRevenueBTC_b = CoinbaseOutputValue_b
```

This metric is different from `obm_issuance_btc_daily`. Daily issuance isolates newly created BTC, while miner revenue includes both newly issued BTC and fees paid by users.

## Interpretation

`obm_miner_revenue_btc_daily` measures the BTC-denominated compensation received by miners for blocks assigned to each UTC calendar day.

This metric is useful for:

- studying miner incentives;
- analyzing Bitcoin's security budget;
- comparing subsidy revenue and fee revenue over time;
- studying the transition from subsidy-dominated to fee-supported miner compensation;
- interpreting halving events and their effect on miner revenue;
- building econometric datasets for Bitcoin research.

The series should be interpreted as miner revenue measured in BTC, not in fiat currency. It does not account for the market price of Bitcoin, mining costs, electricity costs, hardware costs, pool fees, or operating margins.

To obtain fiat-denominated miner revenue, this series would need to be combined with an external BTC/USD price series. Such a derived metric would no longer be purely full-node-derived.

## Data format

The CSV file follows the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_miner_revenue_btc_daily,925.43123456,BTC,daily,OBM v0.1.0
2024-01-02,obm_miner_revenue_btc_daily,888.92187654,BTC,daily,OBM v0.1.0
```

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_miner_revenue_btc_daily` |
| `value` | Miner revenue assigned to the UTC date |
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
5. reads the first transaction in the block, that is, the coinbase transaction;
6. sums the output values of the coinbase transaction;
7. adds the resulting BTC amount to the daily miner-revenue total;
8. writes the resulting time series to CSV.

The script uses a safety height margin around the estimated date interval because Bitcoin block timestamps are not strictly monotonic in block height. This reduces the risk of missing blocks near daily boundaries.

## Typical script usage

Generate the CSV file:

```bash
python3 compute_obm_miner_revenue_btc_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_miner_revenue_btc_daily.csv
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_miner_revenue_btc_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_miner_revenue_btc_daily.csv \
  --plot \
  --plot_output figures/obm_miner_revenue_btc_daily.png
```

## Time needed for complete execution 

For reference, execution time should be similar to other block-scanning scripts that retrieve decoded blocks. It is expected to be slower than `obm_block_count_daily`, because the script must retrieve decoded transaction data to read coinbase output values, but much faster than UTXO-age metrics such as Bitcoin Days Destroyed.

A precise execution-time benchmark should be added after a complete historical run on the reference OBM machine.

## Requirements

The generation script assumes:

- a synchronized Bitcoin Core full node;
- access to the Bitcoin Core JSON-RPC interface;
- Python 3;
- `matplotlib`, only if plot generation is requested.

This metric does not require reconstruction of previous transaction outputs, address extraction, UTXO-set reconstruction, external price data, or third-party APIs.

It does require decoded block data, because the script must read the output values of the coinbase transaction.

## Validation

The following internal checks are recommended:

- verify that every requested date appears exactly once;
- check that values are non-negative BTC amounts;
- confirm that the scanned block-height range covers the requested dates;
- verify that each processed block contains a non-empty transaction list;
- verify that the first transaction in each block is the coinbase transaction;
- compare daily miner revenue with the sum of daily issuance and daily transaction fees once both source series are available;
- inspect days around halving events carefully.

The most important consistency relation is:

```text
obm_miner_revenue_btc_daily = obm_issuance_btc_daily + obm_fees_btc_daily
```

up to any differences caused by timestamp conventions, implementation bugs, or later revisions.

External comparisons should be interpreted cautiously because providers may differ in timestamp conventions, reorganization policies, treatment of historical edge cases, or daily-boundary rules.

## Known limitations

Take into account that this metric:

- measures miner revenue in BTC, not in USD or any other fiat currency;
- includes both newly issued BTC and transaction fees;
- does not measure miner profit, mining costs, energy costs, hardware costs, or operating margins;
- depends on the block timestamp convention used to assign blocks to calendar days;
- may vary from day to day because the number of blocks assigned to each UTC day varies;
- is affected by halving events, fee-market conditions, and block-production variance.

Despite these facts, `obm_miner_revenue_btc_daily` is a central OBM series. It provides a transparent measure of BTC-denominated miner compensation and is useful for studying Bitcoin's security budget, miner incentives, halving dynamics, and the transition from subsidy-based to fee-based revenue.

## Suggested citation

A formal citation will be added once the dataset receives a DOI.

For now, please cite this repository as:

```text
Llanos, D. R. Open Bitcoin Metrics: Reproducible Full-Node-Derived Bitcoin On-Chain Time Series
Metric: Daily Miner Revenue in BTC (obm_miner_revenue_btc_daily).
GitHub repository, version OBM v0.1.0.
https://github.com/diegorllanos/open-bitcoin-metrics/
```

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
