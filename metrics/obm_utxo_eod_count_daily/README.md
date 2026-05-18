# Open Bitcoin Metrics: End-of-Day UTXO Count

This repository provides the following time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_utxo_eod_count_daily
```

The series reports the number of spendable unspent transaction outputs after processing the highest-height block assigned to each UTC calendar day.

The computation script is:

```text
compute_obm_utxo_eod_count_daily_v2.py
```

## Metric summary

| Field | Value |
|---|---|
| Series identifier | `obm_utxo_eod_count_daily` |
| Display name | End-of-day UTXO count |
| Unit | `outputs` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Direct Bitcoin Core block scan |
| External data required | No |
| Main use | UTXO set growth, scalability analysis, node-state burden, network-state diagnostics |

## Definition

`obm_utxo_eod_count_daily` measures the number of spendable unspent transaction outputs after processing the highest-height block assigned to a given UTC calendar day.

Let `UTXOCountAfter_b` denote the number of spendable UTXOs after block `b` has been processed. Let `B_d` denote the set of blocks assigned to UTC date `d`. The metric is defined as:

```text
UTXOCountEOD_d =
    UTXOCountAfter_b*
```

where:

```text
b* = highest-height block in B_d
```

A block is assigned to a UTC calendar date using its block timestamp as returned by Bitcoin Core:

```text
d(b) = UTCDate(block_time_b)
```

If no block is assigned to date `d`, the value is undefined and is written as:

```text
NaN
```

This is because there is no end-of-day block under the selected UTC block-timestamp convention.

## Why the metric is cumulative

The UTXO count is a protocol-state variable. It cannot be computed for an arbitrary start date by looking only at blocks from that date onward, unless the UTXO count at the start date is already known.

The script therefore supports two modes:

```text
1. Genesis mode
2. Checkpoint mode
```

### Genesis mode

Genesis mode is used when:

```text
--start_date 2009-01-03
```

and no checkpoint value is supplied.

In this mode, the script starts with:

```text
utxo_count = 0
```

before block 0, scans the chain forward, and reconstructs the UTXO count from genesis.

### Checkpoint mode

Checkpoint mode is used when the user supplies:

```text
--start_date_eod_utxo_count
```

This value is interpreted as the trusted UTXO count at the end of `--start_date`, under the same counting convention used by this script.

If `--start_date` is different from:

```text
2009-01-03
```

then `--start_date_eod_utxo_count` is mandatory.

In checkpoint mode, the script:

1. writes the supplied UTXO count for `--start_date`;
2. finds the highest-height block assigned to `--start_date` or earlier;
3. starts block-by-block computation from the following chain position;
4. computes subsequent end-of-day UTXO counts normally.

This avoids rescanning the entire blockchain when a trusted end-of-start-day UTXO count is already available.

## Update rule

The script computes the UTXO count by scanning blocks in chain-height order and maintaining a single integer state variable:

```text
utxo_count
```

For each processed block:

```text
utxo_count =
    previous_utxo_count
    + number of spendable outputs created in the block
    - number of previous outputs spent by non-coinbase inputs in the block
```

Equivalently:

```text
UTXOCountAfter_b =
    UTXOCountBefore_b
    + CreatedSpendableOutputs_b
    - SpentOutputs_b
```

where:

```text
CreatedSpendableOutputs_b =
    number of transaction outputs in block b that are not provably unspendable
```

and:

```text
SpentOutputs_b =
    number of inputs in non-coinbase transactions in block b
```

Coinbase inputs are not counted as spent outputs because they do not spend previous UTXOs.

## Coinbase outputs

Coinbase transaction outputs are included when they are not provably unspendable.

This is intentional. Coinbase outputs are part of the UTXO set after they are created, even though they are subject to the coinbase maturity rule before they can be spent.

Therefore, the metric does not exclude immature coinbase outputs. It counts membership in the UTXO set, not immediate spendability under the coinbase maturity rule.

## Provably unspendable outputs

The script excludes outputs that are provably unspendable at creation time.

In decoded Bitcoin Core block data, standard `OP_RETURN` outputs are normally represented as:

```text
scriptPubKey.type = "nulldata"
```

The script excludes such outputs. It also defensively excludes outputs whose script hex begins with:

```text
6a
```

which corresponds to `OP_RETURN`.

This convention is intended to align the metric with the practical concept of the UTXO set, where provably unspendable outputs are not retained as spendable unspent outputs.

## Interpretation

`obm_utxo_eod_count_daily` measures the size of the Bitcoin UTXO set, expressed as a count of outputs.

The metric is useful for:

- studying UTXO set growth;
- analyzing the long-run state burden imposed on Bitcoin nodes;
- comparing output creation and spending dynamics;
- complementing transaction count, spent-output count, raw output value, and block weight;
- supporting scalability and node-resource research;
- identifying periods of UTXO expansion or consolidation.

The metric should not be interpreted as transaction count, address count, user count, entity count, economic activity, or value transferred. A UTXO is an output-level accounting object. A single user or wallet can create many UTXOs, and many UTXOs can be controlled by the same entity.

## Data source and input requirements

The metric is computed directly from a running Bitcoin Core full node through the JSON-RPC interface.

For each block in the scan interval, the script retrieves the decoded block using:

```text
getblock <block_hash> 2
```

The script reads:

- each transaction input;
- each transaction output;
- each output's decoded `scriptPubKey`.

This metric requires:

- a synchronized Bitcoin Core full node;
- JSON-RPC access to the node;
- access to decoded block and transaction data.

This metric does not require:

- the OBM spent-output indexer database;
- `txindex=1`;
- previous-output reconstruction;
- address extraction;
- user clustering;
- entity identification;
- external price data;
- third-party APIs.

Although this metric scans all transactions, it does not resolve inputs to previous transactions. Each non-coinbase input spends exactly one UTXO, so the UTXO count can be updated using input counts rather than previous-output lookups.

## Reproducibility

The metric is generated by scanning blocks in chain-height order and maintaining the UTXO count state.

For each selected date interval, the script:

1. connects to Bitcoin Core through JSON-RPC;
2. obtains the current chain tip using `getblockchaininfo`;
3. validates whether genesis mode or checkpoint mode should be used;
4. in genesis mode, initializes the UTXO count to zero and scans from block 0;
5. in checkpoint mode, initializes the UTXO count with `--start_date_eod_utxo_count`;
6. in checkpoint mode, locates the checkpoint boundary at the end of `--start_date`;
7. locates an approximate ending height for the requested `--end_date`;
8. expands the checkpoint and ending height searches using `--height_margin`;
9. retrieves decoded blocks with `getblock <block_hash> 2`;
10. counts non-provably-unspendable outputs created by all transactions, including coinbase transactions;
11. counts one spent output for each non-coinbase transaction input;
12. updates the running UTXO count after each block;
13. assigns each block to a UTC date using its block timestamp;
14. stores the UTXO count after the highest-height block assigned to each requested UTC date;
15. writes the supplied checkpoint value for `--start_date` in checkpoint mode;
16. writes `NaN` for selected dates with no assigned block;
17. writes one row per UTC date using the standard OBM schema;
18. optionally generates a plot.

The height-margin expansion is used because Bitcoin block timestamps are not strictly monotonic with respect to block height. The expanded scan interval reduces the risk of missing boundary blocks whose timestamps fall inside the selected ending date or checkpoint boundary.

## Typical script usage

### Canonical full run from genesis

Generate the CSV file from genesis using Bitcoin Core cookie authentication:

```bash
python3 compute_obm_utxo_eod_count_daily_v2.py \
  --start_date 2009-01-03 \
  --end_date 2024-01-31 \
  --use_default_cookie \
  --output data/daily/obm_utxo_eod_count_daily.csv
```

Generate the CSV file and a plot:

```bash
python3 compute_obm_utxo_eod_count_daily_v2.py \
  --start_date 2009-01-03 \
  --end_date 2024-01-31 \
  --use_default_cookie \
  --output data/daily/obm_utxo_eod_count_daily.csv \
  --plot \
  --plot_output figures/obm_utxo_eod_count_daily.png
```

### Checkpoint run from a later start date

If the start date is not `2009-01-03`, the script requires a trusted end-of-start-day UTXO count:

```bash
python3 compute_obm_utxo_eod_count_daily_v2.py \
  --start_date 2020-01-01 \
  --end_date 2024-01-31 \
  --start_date_eod_utxo_count 64500000 \
  --use_default_cookie \
  --output data/daily/obm_utxo_eod_count_daily.csv
```

In this example, the value `64500000` is interpreted as the UTXO count at the end of `2020-01-01` under the same counting convention used by this script. The script writes that value for `2020-01-01` and starts updating the counter from the following chain position.

### Explicit RPC credentials

Generate the CSV file using explicit RPC credentials:

```bash
python3 compute_obm_utxo_eod_count_daily_v2.py \
  --start_date 2009-01-03 \
  --end_date 2024-01-31 \
  --rpc_url http://127.0.0.1:8332 \
  --rpc_user my_rpc_user \
  --rpc_password my_rpc_password \
  --output data/daily/obm_utxo_eod_count_daily.csv
```

RPC credentials can also be supplied through environment variables:

```bash
export BITCOIN_RPC_URL="http://127.0.0.1:8332"
export BITCOIN_RPC_USER="my_rpc_user"
export BITCOIN_RPC_PASSWORD="my_rpc_password"
```

Then run:

```bash
python3 compute_obm_utxo_eod_count_daily_v2.py \
  --start_date 2009-01-03 \
  --end_date 2024-01-31 \
  --output data/daily/obm_utxo_eod_count_daily.csv
```

## Command-line arguments

| Argument | Description |
|---|---|
| `--start_date` | Starting UTC output date, inclusive, in `YYYY-MM-DD` format |
| `--end_date` | Ending UTC output date, inclusive, in `YYYY-MM-DD` format |
| `--start_date_eod_utxo_count` | Trusted UTXO count at the end of `--start_date`; mandatory unless `--start_date` is `2009-01-03` |
| `--rpc_url` | Bitcoin Core RPC URL |
| `--rpc_user` | Bitcoin Core RPC username |
| `--rpc_password` | Bitcoin Core RPC password |
| `--cookie_path` | Path to Bitcoin Core RPC cookie file |
| `--use_default_cookie` | Use the default cookie path `~/.bitcoin/.cookie` |
| `--rpc_timeout` | RPC timeout in seconds |
| `--height_margin` | Extra blocks scanned around the checkpoint boundary and after the approximate ending height |
| `--output` | Output CSV file path |
| `--release_version` | Dataset release version written to the output |
| `--plot` | Generate a plot of the resulting series |
| `--plot_output` | Output path for the plot |
| `--quiet` | Suppress diagnostic messages printed to standard error |

The default output file is:

```text
obm_utxo_eod_count_daily.csv
```

The default release version is:

```text
OBM v0.1.0
```

The default height margin is:

```text
288 blocks
```

This corresponds to approximately two days of expected Bitcoin block production.

## Data format

The output CSV file follows the standard OBM scalar schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2009-01-03,obm_utxo_eod_count_daily,1,outputs,daily,OBM v0.1.0
2009-01-04,obm_utxo_eod_count_daily,NaN,outputs,daily,OBM v0.1.0
2024-01-01,obm_utxo_eod_count_daily,160123456,outputs,daily,OBM v0.1.0
```

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM identifier: `obm_utxo_eod_count_daily` |
| `value` | End-of-day UTXO count, or `NaN` when undefined |
| `unit` | Measurement unit: `outputs` |
| `frequency` | Observation frequency: `daily` |
| `release_version` | OBM dataset release version |

## Missing-value convention

The script writes:

```text
NaN
```

when no block is assigned to a selected UTC date. This can occur in the very early history of Bitcoin.

This is preferable to writing zero because the metric is defined as the UTXO count after the highest-height block assigned to the date. If there is no such block, the end-of-day observation is undefined under the selected convention.

In checkpoint mode, the script writes the supplied `--start_date_eod_utxo_count` for `--start_date`, even if it does not rescan blocks for that date.

Users who need a fully filled state series may forward-fill `obm_utxo_eod_count_daily` after export, but such forward-filling is a downstream transformation and is not part of the primary OBM definition.

## Precision

The UTXO count is an integer quantity. The script maintains the count using integer arithmetic and writes integer values to the output CSV.

No floating-point arithmetic is required for the metric itself.

## Validation

Validation is divided into two groups: checks performed directly by the script, and additional checks that are advisable for release preparation or independent auditing.

### Checks performed by the script

The script performs the following checks during execution:

- verifies that `--start_date` is not later than `--end_date`;
- verifies that `--height_margin` is non-negative;
- verifies that `--start_date_eod_utxo_count`, when provided, is non-negative;
- verifies that `--start_date_eod_utxo_count` is provided when `--start_date` is different from `2009-01-03`;
- verifies that the RPC authentication configuration is valid;
- verifies that the RPC cookie file exists and has valid format when cookie authentication is used;
- connects to Bitcoin Core through JSON-RPC;
- obtains the current chain tip using `getblockchaininfo`;
- locates an approximate ending height for the requested date range;
- expands the ending height using `--height_margin`;
- in checkpoint mode, locates the highest-height block assigned to `--start_date` or earlier;
- scans blocks in chain-height order after the selected starting point;
- retrieves decoded blocks using `getblock` with verbosity level 2;
- excludes provably unspendable outputs at creation time;
- counts all non-provably-unspendable outputs created by coinbase and non-coinbase transactions;
- subtracts one UTXO for each non-coinbase transaction input;
- verifies that the running UTXO count never becomes negative;
- assigns each processed block to a UTC date using the block timestamp;
- records the UTXO count after the highest-height block assigned to each selected date;
- writes the checkpoint value for `--start_date` in checkpoint mode;
- writes `NaN` for selected dates with no assigned block;
- writes one output row per selected UTC date;
- writes the output using the standard OBM schema;
- optionally generates a plot when `--plot` is used;
- prints diagnostics including checkpoint mode, checkpoint height, scanned blocks, counted blocks, created spendable outputs, spent outputs, excluded provably unspendable outputs, and final scanned UTXO count, unless `--quiet` is used.

These checks ensure that the script applies a consistent UTXO-counting convention, avoids negative state, and records one end-of-day observation per selected date.

### Recommended additional checks

The following checks are not performed automatically by the script, but are recommended before publishing a release or using the series in empirical work:

- verify that every requested output date appears exactly once in the output CSV;
- verify that all defined values are non-negative integers;
- verify that `NaN` values occur only on dates with no assigned block under the same UTC timestamp convention;
- compare dates with defined values against `obm_block_count_daily`: dates with positive block count should have defined UTXO count;
- compare final UTXO count near the chain tip with Bitcoin Core's `gettxoutsetinfo` output under the same node and chain state;
- in checkpoint mode, independently verify the supplied `--start_date_eod_utxo_count`;
- in checkpoint mode, verify that the first output row equals the supplied checkpoint value;
- verify that daily changes satisfy:
  ```text
  Delta UTXO count =
      spendable outputs created
      - non-coinbase inputs spent
  ```
  when corresponding daily created-output and spent-output counts are available;
- inspect unusually large positive changes as possible UTXO-splitting events;
- inspect unusually large negative changes as possible UTXO-consolidation events;
- compare selected periods with independent public UTXO-count data providers as diagnostics;
- document any differences caused by provably unspendable output treatment.

External comparisons should be interpreted cautiously because providers may differ in timestamp convention, treatment of provably unspendable outputs, forward-filling rules, chain-state snapshot convention, or reorganization handling.

## Relationship with other OBM metrics

This metric is closely related to:

```text
obm_spent_output_count_daily
obm_tx_count_daily
obm_block_count_daily
obm_block_weight_wu_daily
obm_raw_output_value_btc_daily
```

The relationship with spent-output count is especially important. The UTXO count increases when new spendable outputs are created and decreases when outputs are spent. Therefore, daily changes in the UTXO count are governed by:

```text
Delta UTXO count =
    created spendable output count
    - spent output count
```

where the spent-output count corresponds to non-coinbase inputs and the created-output count includes spendable coinbase and non-coinbase outputs.

`obm_utxo_eod_count_daily` can therefore complement `obm_spent_output_count_daily` by providing a state-variable view of the cumulative result of output creation and spending.

## Known limitations

Take into account that this metric:

- reports an end-of-day state variable, not a daily flow;
- is defined using the highest-height block assigned to each UTC date;
- writes `NaN` for dates with no assigned block;
- requires either a genesis scan or a trusted start-date checkpoint;
- depends on the correctness of `--start_date_eod_utxo_count` in checkpoint mode;
- depends on the block timestamp convention used to assign blocks to UTC dates;
- excludes provably unspendable outputs using the decoded script information available from Bitcoin Core;
- includes immature coinbase outputs because they are part of the UTXO set;
- does not identify addresses, users, wallets, entities, exchanges, custodians, or ownership;
- does not measure value held unless paired with a UTXO-value metric;
- does not require the spent-output indexer;
- may differ from provider series that use different rules for unspendable outputs or that forward-fill missing dates.

Despite these limitations, `obm_utxo_eod_count_daily` is a useful OBM network-state series. It provides a transparent, full-node-derived measure of UTXO set size and complements block, transaction, spent-output, and block-space metrics.

## Suggested citation

A formal citation will be added once the dataset receives a DOI.

For now, please cite this repository as:

```text
Llanos, D. R. Open Bitcoin Metrics: Reproducible Full-Node-Derived Bitcoin On-Chain Time Series
Metric: End-of-Day UTXO Count (obm_utxo_eod_count_daily).
GitHub repository, version OBM v0.1.0.
https://github.com/diegorllanos/open-bitcoin-metrics/
```

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
