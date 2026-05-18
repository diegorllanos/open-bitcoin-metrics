# Open Bitcoin Metrics: Estimated 7-Day Network Hashrate in EH/s

This repository provides the following time series of the **Open Bitcoin Metrics (OBM)** project:

```text
obm_est7d_hashrate_ehs_daily
```

The series reports an estimated Bitcoin network hashrate, in exahashes per second, inferred from block-level difficulty and realized block production over a trailing 7-day rolling block-timestamp window.

The computation script is:

```text
compute_obm_est7d_hashrate_ehs_daily.py
```

## Metric summary

| Field | Value |
|---|---|
| Canonical series identifier | `obm_est7d_hashrate_ehs_daily` |
| Display name | Estimated 7-day network hashrate in EH/s |
| Unit | `EH/s` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Direct Bitcoin Core block-metadata scan |
| External data required | No |
| Default window | 7 trailing calendar days |
| Main use | Mining activity, network security proxy, difficulty and miner-incentive analysis |

## Naming convention

The canonical OBM metric is:

```text
obm_est7d_hashrate_ehs_daily
```

The `est7d` component is part of the series identifier because the window length is part of the metric definition. Hashrate is not directly observed on-chain, and estimates based on different rolling windows can differ materially. A 7-day estimate, a 14-day estimate, and a 30-day estimate should therefore not share the same `series_id`.

The script implements dynamic series naming:

```text
--window_days 7  -> obm_est7d_hashrate_ehs_daily
--window_days 14 -> obm_est14d_hashrate_ehs_daily
--window_days 30 -> obm_est30d_hashrate_ehs_daily
```

If the `--output` argument is omitted, the output filename is also derived from the selected window:

```text
--window_days 7  -> obm_est7d_hashrate_ehs_daily.csv
--window_days 14 -> obm_est14d_hashrate_ehs_daily.csv
--window_days 30 -> obm_est30d_hashrate_ehs_daily.csv
```

This behavior prevents accidentally publishing a 14-day or 30-day estimate under the canonical 7-day series identifier.

## Definition

`obm_est7d_hashrate_ehs_daily` estimates the Bitcoin network hashrate from block difficulty and realized block production.

Hashrate is not directly observed on-chain. It must be inferred from the amount of proof-of-work implied by blocks found over a time interval.

For each UTC date `d`, the canonical 7-day window is the trailing interval ending at 23:59:59 UTC on date `d`:

```text
W_d = blocks with timestamps in [d - 6 days 00:00:00 UTC, d 23:59:59 UTC]
```

For each block `b` in the window, let:

```text
Difficulty_b
```

be the mining difficulty reported by Bitcoin Core for that block.

The estimated hashrate in hashes per second is:

```text
EstimatedHashrateHPS_d =
    sum_{b in W_d} Difficulty_b * 2^32
    /
    elapsed_seconds_d
```

where:

```text
elapsed_seconds_d =
    max block timestamp in W_d - min block timestamp in W_d
```

The value is converted to exahashes per second as:

```text
EstimatedHashrateEHS_d =
    EstimatedHashrateHPS_d / 10^18
```

The output unit is:

```text
EH/s
```

## Interpretation

`obm_est7d_hashrate_ehs_daily` is an estimate of the aggregate computational rate devoted to Bitcoin mining over a trailing 7-day window.

The metric is useful for:

- studying mining activity;
- proxying aggregate network security conditions;
- complementing difficulty, block count, fees, and miner revenue;
- supporting mining and energy-related empirical studies;
- analyzing how miner incentives relate to estimated computational activity;
- constructing indicators of mining-sector response to market conditions.

The metric should not be interpreted as a directly observed quantity. It is inferred from difficulty and realized block arrival times. Because block discovery is stochastic, short-window estimates are noisy. The 7-day trailing window smooths part of this randomness while still producing a daily series.

## Why a 7-day rolling window?

A one-day estimate would be very noisy because Bitcoin block discovery is probabilistic. A UTC day may contain more or fewer blocks than expected even if the underlying hashrate is unchanged.

For this reason, the OBM baseline uses:

```text
--window_days 7
```

This window length is a compromise between smoothness and responsiveness. Longer windows, such as 14 or 30 days, are smoother but slower to react. Shorter windows are more responsive but noisier.

Alternative windows can be computed by changing:

```text
--window_days
```

However, such outputs are different metrics. The script records this difference automatically in the `series_id` and, unless explicitly overridden, in the output filename.

## Data source and input requirements

The metric is computed directly from a running Bitcoin Core full node through the JSON-RPC interface.

For each block in the scan interval, the script retrieves decoded block metadata using:

```text
getblock <block_hash> 1
```

The script uses the block-level fields:

```text
time
difficulty
height
```

This metric requires:

- a synchronized Bitcoin Core full node;
- JSON-RPC access to the node;
- access to decoded block metadata.

This metric does not require:

- the OBM spent-output indexer database;
- `txindex=1`;
- previous-output reconstruction;
- transaction-level scanning;
- address extraction;
- user clustering;
- entity identification;
- external price data;
- third-party APIs.

Although `txindex=1` is useful for other OBM metrics, it is not required here because the metric uses only block-level metadata.

## Reproducibility

The metric is generated by scanning block metadata over an expanded date interval and computing a rolling-window hashrate estimate for each output date.

For each selected date interval, the script:

1. connects to Bitcoin Core through JSON-RPC;
2. obtains the current chain tip using `getblockchaininfo`;
3. expands the required scan date range backward by `window_days - 1` days;
4. identifies an approximate block-height interval covering the expanded UTC date range;
5. expands the interval using `--height_margin`;
6. scans every block in the expanded interval;
7. assigns each block to a UTC calendar date using the block timestamp;
8. keeps only blocks whose timestamps fall inside the window-expanded scan dates;
9. reads each counted block's `difficulty` field;
10. sorts blocks by timestamp, with height used to break ties;
11. for each output date, selects blocks in the trailing rolling window;
12. requires at least `--min_blocks` blocks in the window;
13. computes the elapsed time between the first and last block in the window;
14. computes the estimate:
    ```text
    sum(difficulty_b * 2^32) / elapsed_seconds / 10^18
    ```
15. writes `NaN` when the estimate is undefined;
16. writes one row per UTC output date using the standard OBM schema;
17. uses a window-specific `series_id`, such as `obm_est7d_hashrate_ehs_daily` or `obm_est14d_hashrate_ehs_daily`;
18. optionally generates a plot.

The height-margin expansion is used because Bitcoin block timestamps are not strictly monotonic with respect to block height. The expanded scan interval reduces the risk of missing boundary blocks whose timestamps fall inside the rolling windows.

## Typical script usage

Generate the canonical 7-day CSV file using Bitcoin Core cookie authentication:

```bash
python3 compute_obm_est7d_hashrate_ehs_daily.py \
  --start_date 2009-01-01 \
  --end_date 2024-01-31 \
  --window_days 7 \
  --min_blocks 2 \
  --use_default_cookie
```

Because `--output` is omitted, the script writes:

```text
obm_est7d_hashrate_ehs_daily.csv
```

Generate the canonical 7-day CSV file and a plot:

```bash
python3 compute_obm_est7d_hashrate_ehs_daily.py \
  --start_date 2009-01-01 \
  --end_date 2024-01-31 \
  --window_days 7 \
  --min_blocks 2 \
  --use_default_cookie \
  --output data/daily/obm_est7d_hashrate_ehs_daily.csv \
  --plot \
  --plot_output figures/obm_est7d_hashrate_ehs_daily.png
```

Generate a 14-day variant:

```bash
python3 compute_obm_est7d_hashrate_ehs_daily.py \
  --start_date 2009-01-01 \
  --end_date 2024-01-31 \
  --window_days 14 \
  --min_blocks 2 \
  --use_default_cookie
```

Because `--output` is omitted, the script writes:

```text
obm_est14d_hashrate_ehs_daily.csv
```

and the `series_id` column is:

```text
obm_est14d_hashrate_ehs_daily
```

Generate the CSV file using explicit RPC credentials:

```bash
python3 compute_obm_est7d_hashrate_ehs_daily.py \
  --start_date 2009-01-01 \
  --end_date 2024-01-31 \
  --rpc_url http://127.0.0.1:8332 \
  --rpc_user my_rpc_user \
  --rpc_password my_rpc_password \
  --output data/daily/obm_est7d_hashrate_ehs_daily.csv
```

RPC credentials can also be supplied through environment variables:

```bash
export BITCOIN_RPC_URL="http://127.0.0.1:8332"
export BITCOIN_RPC_USER="my_rpc_user"
export BITCOIN_RPC_PASSWORD="my_rpc_password"
```

Then run:

```bash
python3 compute_obm_est7d_hashrate_ehs_daily.py \
  --start_date 2009-01-01 \
  --end_date 2024-01-31
```

## Command-line arguments

| Argument | Description |
|---|---|
| `--start_date` | Starting UTC output date, inclusive, in `YYYY-MM-DD` format |
| `--end_date` | Ending UTC output date, inclusive, in `YYYY-MM-DD` format |
| `--window_days` | Length of the trailing rolling calendar-day window |
| `--min_blocks` | Minimum number of blocks required in a window for a defined estimate |
| `--rpc_url` | Bitcoin Core RPC URL |
| `--rpc_user` | Bitcoin Core RPC username |
| `--rpc_password` | Bitcoin Core RPC password |
| `--cookie_path` | Path to Bitcoin Core RPC cookie file |
| `--use_default_cookie` | Use the default cookie path `~/.bitcoin/.cookie` |
| `--rpc_timeout` | RPC timeout in seconds |
| `--height_margin` | Extra blocks scanned before and after the approximate height interval |
| `--output` | Optional output CSV file path |
| `--release_version` | Dataset release version written to the output |
| `--plot` | Generate a plot of the resulting series |
| `--plot_output` | Output path for the plot |
| `--quiet` | Suppress diagnostic messages printed to standard error |

The default rolling window is:

```text
7 calendar days
```

The default minimum number of blocks is:

```text
2
```

The default height margin is:

```text
2016 blocks
```

A larger height margin is used here than in simple daily block-level metrics because the script needs to collect blocks over rolling windows that extend before the first output date.

## Data format

The output CSV file follows the standard OBM scalar schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example for the canonical 7-day series:

```csv
date,series_id,value,unit,frequency,release_version
2009-01-03,obm_est7d_hashrate_ehs_daily,NaN,EH/s,daily,OBM v0.1.0
2024-01-01,obm_est7d_hashrate_ehs_daily,512.345678901234,EH/s,daily,OBM v0.1.0
2024-01-02,obm_est7d_hashrate_ehs_daily,509.876543210987,EH/s,daily,OBM v0.1.0
```

Example for a 14-day variant:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_est14d_hashrate_ehs_daily,510.123456789012,EH/s,daily,OBM v0.1.0
2024-01-02,obm_est14d_hashrate_ehs_daily,508.987654321098,EH/s,daily,OBM v0.1.0
```

### Columns

| Column | Description |
|---|---|
| `date` | UTC calendar output date in `YYYY-MM-DD` format |
| `series_id` | Window-specific OBM identifier, for example `obm_est7d_hashrate_ehs_daily` |
| `value` | Estimated network hashrate in exahashes per second, or `NaN` |
| `unit` | Measurement unit: `EH/s` |
| `frequency` | Observation frequency: `daily` |
| `release_version` | OBM dataset release version |

## Missing-value convention

The script writes:

```text
NaN
```

when the rolling-window estimate is undefined.

This can occur when:

- the number of blocks in the window is smaller than `--min_blocks`;
- the elapsed time between the first and last block in the window is zero or negative;
- no valid block metadata are available for the window.

This is preferable to writing zero because a zero hashrate would imply no mining activity, whereas `NaN` indicates that the estimate is undefined under the selected window and minimum-block convention.

## Precision

Difficulty values are parsed using Python's `Decimal` type. The script computes the estimated hashrate using high-precision decimal arithmetic:

```text
estimated_hashrate_ehs =
    sum(difficulty_b * 2^32) / elapsed_seconds / 10^18
```

Defined output values are written with twelve decimal places.

## Validation

Validation is divided into two groups: checks performed directly by the script, and additional checks that are advisable for release preparation or independent auditing.

### Checks performed by the script

The script performs the following checks during execution:

- verifies that `--start_date` is not later than `--end_date`;
- verifies that `--window_days` is at least 1;
- verifies that `--min_blocks` is at least 2;
- verifies that `--height_margin` is non-negative;
- verifies that the RPC authentication configuration is valid;
- verifies that the RPC cookie file exists and has valid format when cookie authentication is used;
- connects to Bitcoin Core through JSON-RPC;
- obtains the current chain tip using `getblockchaininfo`;
- expands the scan date range backward by `window_days - 1` days;
- locates an approximate block-height interval for the expanded timestamp range;
- expands the scan interval using `--height_margin`;
- scans all blocks in the expanded interval;
- assigns each scanned block to a UTC date using the block timestamp;
- keeps only blocks in the window-expanded scan date interval;
- verifies that each counted block contains a `difficulty` field;
- rejects negative difficulty values;
- sorts blocks by timestamp, using height as a tie-breaker;
- counts the number of blocks in each rolling window;
- writes `NaN` when a rolling window has fewer than `--min_blocks` blocks;
- writes `NaN` when the elapsed time between first and last block in the window is not positive;
- derives the output `series_id` from the selected rolling window;
- derives the default output filename from the selected rolling window when `--output` is omitted;
- writes one output row per selected UTC date;
- writes the output using the standard OBM schema;
- optionally generates a plot when `--plot` is used;
- prints diagnostics including counted blocks, scanned blocks, defined observations, `NaN` observations, and the window block-count range, unless `--quiet` is used.

These checks ensure that the script uses block-level difficulty consistently and produces estimates only when the rolling-window data are sufficient.

### Recommended additional checks

The following checks are not performed automatically by the script, but are recommended before publishing a release or using the series in empirical work:

- verify that every requested output date appears exactly once in the output CSV;
- verify that all defined values are positive;
- verify that the output `series_id` matches the selected `--window_days` value;
- verify that the output filename matches the selected `--window_days` value when no custom path is used;
- compare selected dates with independent hashrate estimates from public data providers;
- verify that large changes are consistent with changes in block count, difficulty, or both;
- compare the series with `obm_difficulty_eod_daily`;
- inspect early dates where the number of blocks in the window is small;
- test sensitivity to alternative values of `--window_days`, such as 14 or 30 days;
- document the selected window length whenever the metric is used in empirical work;
- compare the rolling-window block counts with `obm_block_count_daily`;
- inspect the effect of retarget boundaries on the estimate.

External comparisons should be interpreted cautiously because providers may differ in window length, smoothing method, timestamp convention, difficulty convention, whether they use block count or expected inter-block time, and whether they report point estimates or moving averages.

## Relationship with other OBM metrics

This metric is closely related to:

```text
obm_difficulty_eod_daily
obm_block_count_daily
obm_block_weight_wu_daily
obm_miner_revenue_btc_daily
obm_fees_btc_daily
```

Difficulty gives the protocol target. Block count gives realized block production. Estimated hashrate combines difficulty and realized block timing into an inferred computational-rate measure.

The metric should not be derived directly from `obm_difficulty_eod_daily`, because the hashrate estimate needs block-level difficulty over the full rolling window, especially around retarget boundaries.

`obm_est7d_hashrate_ehs_daily` is also useful alongside miner revenue and fees. These series can be used to study whether changes in miner compensation are associated with changes in estimated network hashrate.

## Known limitations

Take into account that this metric:

- is an estimate, not a directly observed on-chain quantity;
- depends on the chosen rolling-window length;
- uses 7 trailing calendar days for the canonical OBM series;
- depends on the minimum-block rule;
- is sensitive to stochastic block arrival, especially for short windows;
- depends on the block timestamp convention used to construct windows;
- uses elapsed time between first and last block timestamps in the window;
- may be noisy in early Bitcoin history or during windows with few blocks;
- does not identify individual miners, mining pools, or geographic mining activity;
- does not measure mining profitability;
- does not directly measure energy consumption;
- is directly computed from decoded block metadata and does not require the spent-output indexer;
- may differ from provider series that use different smoothing windows or formulas.

Despite these limitations, `obm_est7d_hashrate_ehs_daily` is a useful OBM mining-activity series. It provides a transparent, full-node-derived estimate of network hashrate and complements difficulty, block count, fees, miner revenue, and energy-related empirical analyses.

## Suggested citation

A formal citation will be added once the dataset receives a DOI.

For now, please cite this repository as:

```text
Llanos, D. R. Open Bitcoin Metrics: Reproducible Full-Node-Derived Bitcoin On-Chain Time Series
Metric: Estimated 7-Day Network Hashrate in EH/s (obm_est7d_hashrate_ehs_daily).
GitHub repository, version OBM v0.1.0.
https://github.com/diegorllanos/open-bitcoin-metrics/
```

If a non-default window is used, cite the corresponding window-specific metric explicitly, for example:

```text
Metric: Estimated 14-Day Network Hashrate in EH/s (obm_est14d_hashrate_ehs_daily).
```

## License

- MIT License for code;
- CC BY 4.0 for data and documentation.

## Project status

This repository is part of the broader **Open Bitcoin Metrics** project, which aims to provide transparent, reproducible, full-node-derived Bitcoin time series for economic and econometric research.
