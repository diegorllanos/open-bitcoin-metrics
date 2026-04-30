# Open Bitcoin Metrics: Daily Bitcoin Issuance

This repository provides the following time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_issuance_btc_daily
```

The series reports the real daily Bitcoin issuance, measured in BTC, computed directly from a running Bitcoin Core full node.

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_issuance_btc_daily` |
| Display name | Daily Bitcoin issuance |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Bitcoin Core full node |
| External data required | No |
| Main use | Realized monetary issuance, monetary supply analysis, subsidy dynamics |

## Definition

Let B_d denote the set of Bitcoin blocks assigned to UTC calendar day d. For each block b, let C_b denote the total value of the outputs of the coinbase transaction, and let F_b denote the total transaction fees paid by non-coinbase transactions in that block. The real issuance of block b is defined as:

```text
Issuance_b = C_b - F_b
```

The daily Bitcoin issuance is then:

```text
Issuance_d = sum_{b in B_d} Issuance_b
```

A block is assigned to a day according to the UTC date derived from the block timestamp returned by Bitcoin Core.

This metric measures realized issuance, not merely theoretical scheduled issuance. This distinction matters because miners do not necessarily have to claim the full allowed block subsidy. When the coinbase transaction claims less than the maximum allowed amount, actual issuance is lower than the theoretical maximum.

## Interpretation

`obm_issuance_btc_daily` measures how many new bitcoins were actually created on each UTC calendar day.

This metric is useful for:

- studying Bitcoin's realized monetary issuance;
- measuring daily additions to circulating supply;
- distinguishing realized issuance from theoretical subsidy schedules;
- analyzing halving periods and long-run monetary-supply dynamics;
- constructing cumulative supply series;
- building econometric datasets for Bitcoin research.

Bitcoin's protocol defines a maximum block subsidy schedule, but the actual number of bitcoins created in a block is determined by the value claimed in the coinbase transaction after excluding transaction fees. Since transaction fees are paid by existing coins, they are not newly issued supply. Therefore, the script computes real issuance as coinbase output value minus transaction fees.

The series should therefore be interpreted as a daily monetary flow: the number of newly created bitcoins assigned to a UTC calendar day.

## Data format

The CSV file follows the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_issuance_btc_daily,918.75000000,BTC,daily,OBM v0.1.0
2024-01-02,obm_issuance_btc_daily,881.25000000,BTC,daily,OBM v0.1.0
```

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_issuance_btc_daily` |
| `value` | Realized Bitcoin issuance assigned to the UTC date |
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
5. reads the total output value of the coinbase transaction;
6. computes transaction fees from non-coinbase transactions, using fee fields or previous-output information when available;
7. computes block-level realized issuance as coinbase output value minus transaction fees;
8. aggregates realized issuance by UTC date;
9. writes the resulting time series to CSV.

The script uses a safety height margin around the estimated date interval because Bitcoin block timestamps are not strictly monotonic in block height. This reduces the risk of missing blocks near daily boundaries.

## Typical script usage

Generate the CSV file:

```bash
python3 compute_obm_issuance_btc_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_issuance_btc_daily.csv
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_issuance_btc_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_issuance_btc_daily.csv \
  --plot \
  --plot_output figures/obm_issuance_btc_daily.png
```

## Requirements

The generation script assumes:

- a synchronized Bitcoin Core full node;
- access to the Bitcoin Core JSON-RPC interface;
- Python 3;
- `matplotlib`, only if plot generation is requested.

Unlike simpler block-level metrics, this metric requires transaction fee information. The script is designed to retrieve decoded block data with transaction and previous-output information. A non-pruned Bitcoin Core node is strongly recommended, because historical fee reconstruction may require access to undo data.

This metric does not require address extraction, user/entity clustering, external price data, or third-party APIs.

## Validation

The following internal checks are recommended:

- verify that every requested date appears exactly once;
- check that values are non-negative BTC amounts;
- confirm that the scanned block-height range covers the requested dates;
- verify that block-level issuance is non-negative;
- compare daily issuance with the corresponding daily block count and expected subsidy era;
- inspect days around halving events carefully;
- compare selected periods with independently reconstructed issuance or supply data as a diagnostic check.

External comparisons should be interpreted cautiously because providers may use different timestamp conventions, reorganization policies, daily-boundary rules, or may report theoretical issuance rather than realized issuance.

## Known limitations

This metric has several limitations:

- it measures realized issuance, not the theoretical maximum subsidy schedule;
- it depends on accurate reconstruction of transaction fees;
- historical fee reconstruction may require a non-pruned node with the necessary block and undo data;
- it does not include transaction fees as newly issued supply, because fees are transfers of already existing bitcoins;
- it depends on the block timestamp convention used to assign blocks to calendar days;
- daily values vary with the number of blocks assigned to each UTC day, so deviations from the expected daily issuance can reflect normal variation in block production.

Despite these limitations, `obm_issuance_btc_daily` is a central OBM series. It provides a transparent measure of realized monetary issuance and is a building block for cumulative Bitcoin supply, miner-revenue metrics, subsidy-era analysis, and monetary-supply studies.

## Suggested citation

A formal citation will be added once the dataset receives a DOI.

For now, please cite this repository as:

```text
Llanos, D. R. Open Bitcoin Metrics: Reproducible Full-Node-Derived Bitcoin On-Chain Time Series
Metric: Daily Bitcoin Issuance (obm_issuance_btc_daily).
GitHub repository, version OBM v0.1.0.
https://github.com/diegorllanos/open-bitcoin-metrics/
```

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
