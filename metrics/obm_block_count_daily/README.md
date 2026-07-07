# Open Bitcoin Metrics: Daily Block Count

This repository provides the following time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_block_count_daily
```

The series reports the daily number of Bitcoin blocks included in the locally verified Bitcoin main chain, computed 
directly from a running Bitcoin Core full node.

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_block_count_daily` |
| Display name | Daily Bitcoin block count |
| Unit | `blocks` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Bitcoin Core full node |
| External data required | No |
| Main use | Block production, network operation, normalization of block-level metrics |

## Definition

Let \(B_d\) denote the set of Bitcoin blocks assigned to UTC calendar day \(d\). The daily block count is defined as:

```text
BlockCount_d = |B_d|
```

where \(|B_d|\) is the number of blocks whose timestamps fall within UTC calendar day \(d\).

A block is assigned to a day according to the UTC date derived from the block timestamp returned by Bitcoin Core.

## Interpretation

`obm_block_count_daily` is a basic indicator of Bitcoin block production. It measures how many blocks were included in the main chain during each UTC calendar day.

This metric is useful for:

- studying realized block production over time;
- checking deviations from the expected average of approximately 144 blocks per day;
- normalizing other block-level metrics;
- interpreting daily variation in transaction count, fees, block weight, and issuance;
- building econometric datasets for Bitcoin research.

Bitcoin targets an average inter-block interval of approximately 10 minutes, so the expected number of blocks per day is approximately:

```text
24 hours * 6 blocks per hour = 144 blocks per day
```

However, the realized number of blocks per UTC day fluctuates because block discovery is probabilistic, mining difficulty adjusts only periodically, and block timestamps do not necessarily align with exact calendar boundaries.

The series should therefore not be interpreted as a measure of demand or economic activity by itself. Rather, it captures the daily number of blocks available for transaction settlement.

## Data format

The CSV file follows the standard OBM schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_block_count_daily,147,blocks,daily,OBM v0.1.0
2024-01-02,obm_block_count_daily,141,blocks,daily,OBM v0.1.0
```

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_block_count_daily` |
| `value` | Number of Bitcoin blocks assigned to the UTC date |
| `unit` | Measurement unit: `blocks` |
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
5. adds one unit to the daily count for the corresponding day;
6. writes the resulting time series to CSV.

The script uses a safety height margin around the estimated date interval because Bitcoin block timestamps are not strictly monotonic in block height. This reduces the risk of missing blocks near daily boundaries.

## Typical script usage

Generate the CSV file:

```bash
python3 compute_obm_block_count_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_block_count_daily.csv
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_block_count_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_block_count_daily.csv \
  --plot \
  --plot_output figures/obm_block_count_daily.png
```
Both `--start_date` and `--end_date` are interpreted as UTC dates and are included in the output.

### Relevant optional parameters

| Parameter | Meaning | Default |
|---|---|---|
| `--release_version` | Dataset release label written to the CSV file | `OBM v0.1.0` |
| `--rpc_host` | Bitcoin Core RPC host | `127.0.0.1` |
| `--rpc_port` | Bitcoin Core RPC port | `8332` |
| `--rpc_user` | RPC username. If omitted, cookie authentication is used | none |
| `--rpc_password` | RPC password. If omitted, cookie authentication is used | none |
| `--datadir` | Bitcoin Core data directory used to locate `.cookie` | `~/.bitcoin` |
| `--cookie_path` | Explicit path to the Bitcoin Core cookie file | none |
| `--height_margin` | Extra blocks scanned before and after the approximate interval | `288` |
| `--progress_every` | Print progress every N scanned blocks. Use 0 to disable | `1000` |
| `--plot` | Generate a plot | disabled |
| `--plot_output` | Output path for the plot | same path as CSV, with `.png` extension |

## Time needed for complete execution 

For reference, the execution time consumed by this script, on an Intel(R) Core(TM) i5-7400 CPU 
@ 3.00GHz with 32Gb RAM, running Bitcoin Core locally, from 2009-01-01 to 2026-04-29, was 
10678 seconds (around three hours). 

## Requirements

The generation script assumes:

- a synchronized Bitcoin Core full node;
- access to the Bitcoin Core JSON-RPC interface;
- Python 3;
- `matplotlib`, only if plot generation is requested.

This metric does not require transaction-output reconstruction, address extraction, UTXO-set reconstruction, transaction-value parsing, fee computation, or external price data.

## Validation

The following internal checks are recommended:

- verify that every requested date appears exactly once;
- check that values are non-negative integers;
- confirm that the scanned block-height range covers the requested dates;
- verify that the total number of counted blocks equals the number of scanned blocks whose timestamps fall inside the requested date interval;
- compare selected periods with external public Bitcoin data providers as a diagnostic check;
- inspect days with unusually high or unusually low block counts, since these may reflect normal mining variance, difficulty-adjustment dynamics, timestamp effects, or data-extraction issues.

External comparisons should be interpreted cautiously because providers may use different timestamp conventions, reorganization policies, or daily-boundary rules.

## Known limitations

Take into account that this metric:

- depends on the block timestamp convention used to assign blocks to calendar days;
- may present short-run deviations from 144 blocks per day. They are normal and should 
not be interpreted mechanically as changes in network health.

Despite these facts, `obm_block_count_daily` is a useful baseline indicator of Bitcoin block production. It is also valuable as a normalization variable for other OBM metrics, especially transaction count, fees, issuance, miner revenue, block weight, and other block-level aggregates.

## Suggested citation

```text
Llanos, D. R. Open Bitcoin Metrics: Verifiable Full-Node-Derived Bitcoin Time Series for Economic Research
ArXiv preprint, https://arxiv.org/abs/2607.03124
```

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
