# Open Bitcoin Metrics (OBM)

**Open Bitcoin Metrics (OBM)** is an open-data project that provides reproducible Bitcoin on-chain time series for economic, financial, and econometric research.

The project aims to make specialized Bitcoin metrics easier to access, audit, cite, and reproduce. Each metric is accompanied by:

- a CSV time series;
- a Python script that generates the series;
- a clear definition of the metric;
- documentation of the algorithm used to compute it;
- metadata fields intended to support reproducibility and academic use.

The long-term goal is to provide a transparent, full-node-derived dataset of Bitcoin metrics suitable for research papers, replication packages, teaching, and exploratory analysis.

## Motivation

Bitcoin research increasingly relies on on-chain indicators to study network activity, monetary issuance, transaction demand, miner incentives, liquidity conditions, and long-run monetary behavior.

However, many Bitcoin metrics are currently dispersed across commercial dashboards, public websites, and proprietary APIs. Definitions are not always explicit, historical series may be incomplete, and access is sometimes limited by paywalls or usage restrictions.

OBM addresses this problem by providing a reproducible and openly documented alternative. Whenever possible, metrics are reconstructed directly from a Bitcoin Core full node rather than copied from third-party providers.

## Current status

The project is in an early stage. Metrics are being added one at a time, with priority given to robustness, reproducibility, and clear documentation.

The available metrics so far are the following:

- `obm_issuance_btc_daily` reports the real, daily Bitcoin issuance confirmed on-chain.
- `obm_block_count_daily` reports the daily number of Bitcoin blocks confirmed on-chain. 
- `obm_tx_count_daily` reports the daily number of Bitcoin transactions confirmed on-chain.

## Available metrics

| Series identifier | Display name | Frequency | Unit | Status |
|---|---|---|---|---|
| `obm_block_count_daily` | Daily Bitcoin block count | Daily | Transactions | Available |
| `obm_cdd_btcxdays_daily` | Bitcoin Days Destroyed | Coin-age dynamics, long-term holder activity |
| `obm_issuance_btc_daily` | Daily Bitcoin issuance | Daily | BTCs | Available |
| `obm_accum_issuance_btc_daily` | Accumulated Bitcoin supply | Daily | BTCs | Available |
| `obm_tx_count_daily` | Daily Bitcoin transaction count | Daily | Transactions | Available |

## Future  metrics

Future metrics planned for inclusion include:

| Series identifier | Display name | Main use |
|---|---|---|
| `obm_supply_btc_daily` | Circulating Bitcoin supply | Monetary supply, scarcity, normalization |
| `obm_bincdd365d_btc_daily` | Binary Bitcoin Days Destroyed, 365-day threshold | Movement of coins under threshold rules |
| `obm_cdd_supply_adjusted_daily` | Supply-adjusted Bitcoin Days Destroyed | Comparable coin-age activity across eras |
| `obm_dormancy_days_daily` | Dormancy | Average age of coins moved |
| `obm_fees_btc_daily` | Total transaction fees in BTC | Fee market and block-space demand |
| `obm_miner_revenue_btc_daily` | Miner revenue in BTC | Miner incentives and security budget |
| `obm_fees_share_miner_revenue_daily` | Fees as share of miner revenue | Transition from subsidy to fees |
| `obm_block_weight_avg_daily` | Average block weight | Block-space utilization |
| `obm_fee_median_satvbyte_daily` | Median fee rate | Typical transaction cost |
| `obm_spent_value_btc_daily` | Total spent output value | Gross on-chain settlement value |
| `obm_active_addresses_daily` | Active addresses | Approximate network participation |
| `obm_tx_volume_usd_daily` | Transaction volume in USD | Fiat-denominated settlement activity |

The planned list may evolve as definitions are refined and validation procedures are developed.

## Data philosophy

OBM follows five principles.

### 1. Primary-source derivation

Metrics are reconstructed from Bitcoin blockchain data obtained through a Bitcoin Core full node whenever possible.

### 2. Transparent definitions

Each variable is associated with an explicit definition, a stable series identifier, a measurement unit, and a documented computational procedure.

### 3. Econometric usability

Series are distributed in regular time intervals, initially daily, using clear timestamp conventions and aggregation rules.

### 4. Reproducibility

Each metric is accompanied by the Python script used to generate it. The objective is that a researcher with a synchronized Bitcoin node can reproduce the published values.

### 5. Versioning

Dataset releases use explicit release labels, for example:

```text
OBM v0.1.0
```

This allows researchers to cite and reproduce the exact version used in their work.

## Standard CSV schema

Each OBM time series uses the following canonical schema:

```text
date,series_id,value,unit,frequency,release_version
```

Example:

```csv
date,series_id,value,unit,frequency,release_version
2024-01-01,obm_tx_count_daily,731566,transactions,daily,OBM v0.1.0
2024-01-02,obm_tx_count_daily,649123,transactions,daily,OBM v0.1.0
```

### Column descriptions

| Column | Description |
|---|---|
| `date` | UTC calendar date in `YYYY-MM-DD` format |
| `series_id` | Stable OBM series identifier |
| `value` | Observed value |
| `unit` | Measurement unit |
| `frequency` | Observation frequency |
| `release_version` | OBM dataset release version |

The schema is intentionally slightly redundant. The goal is to make each file self-describing, even when copied, merged, archived, or used outside the repository.

## Naming convention

OBM series identifiers follow lowercase snake case:

```text
obm_<metric>_<unit_or_variant>_<frequency>
```

Examples:

```text
obm_tx_count_daily
obm_supply_btc_daily
obm_fees_btc_daily
```

The `obm_` prefix identifies the Open Bitcoin Metrics dataset and reduces ambiguity when OBM series are merged with external macro-financial variables.

## Repository structure

The repository structure is the following:

```text
open-bitcoin-metrics/
    obm_issuance_btc_daily/
    obm_tx_count_daily/
    obm_block_count_daily/
    README.md
    CITATION.cff
    DATA_LICENSE
    LICENSE
    plot_obm_csv.py
```

Inside each metric directory there are three files: the "compute" Python script; the CSV file and a 
PNG containing a plot representing the metric. 

The structure will expand as additional metrics are added.

## Reproducibility requirements

OBM scripts assume:

- a synchronized Bitcoin Core full node;
- access to the Bitcoin Core JSON-RPC interface;
- Python 3;
- a Linux environment for scheduled execution;
- optional plotting libraries, such as `matplotlib`, when plots are requested.

Some future metrics, especially UTXO-age metrics such as Bitcoin Days Destroyed, may require additional indexing or reconstruction of previous transaction outputs.

## Example usage

General format of command-line parameters:


```bash
compute_obm_block_count_daily.py [-h] 
   --start_date START_DATE 
   --end_date END_DATE 
   [--output OUTPUT]
   [--release_version RELEASE_VERSION] 
   [--rpc_host RPC_HOST]
   [--rpc_port RPC_PORT] 
   [--rpc_user RPC_USER]
   [--rpc_password RPC_PASSWORD] 
   [--datadir DATADIR]
   [--cookie_path COOKIE_PATH] 
   [--height_margin HEIGHT_MARGIN]
   [--progress_every PROGRESS_EVERY] 
   [--plot]
   [--plot_output PLOT_OUTPUT]
```

For example, the following invocation generates the daily transaction-count series and 
the corresponding plot:

```bash
python3 scripts/compute_obm_tx_count_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output data/daily/obm_tx_count_daily.csv \
  --release_version "OBM v0.1.0"
  --plot \
  --plot_output data/obm_tx_count_daily/obm_tx_count_daily.png
```

Finally, to plot any OBM-compatible CSV file:

```bash
python3 scripts/plot_obm_csv.py data/daily/obm_tx_count_daily.csv \
  --output data/obm_tx_count_daily/obm_tx_count_daily.png
```

## Validation

Validation is metric-specific, but OBM generally relies on three types of checks:

1. **Internal consistency checks**, such as missing dates, duplicate dates, negative values, or inconsistent totals.
2. **Reproducibility checks**, ensuring that scripts can regenerate the published series from the documented inputs.
3. **External comparisons**, when comparable public series are available.

External comparisons are diagnostic rather than definitive. Data providers may differ in timestamp conventions, treatment of chain reorganizations, inclusion rules, or metric definitions.

## Known limitations

OBM metrics should be interpreted carefully.

- On-chain transactions do not map one-to-one to users.
- On-chain transactions do not map one-to-one to economically distinct payments.
- Address-based metrics require heuristics and should not be interpreted as user counts.
- Gross transaction-value metrics can include self-transfers, change outputs, and exchange activity.
- USD-denominated metrics require external price data and are therefore not purely full-node-derived.
- Daily aggregation depends on timestamp conventions.
- Daily rolling releases may be revised if bugs, edge cases, or definitional improvements are identified.

## Suggested citation

A formal citation will be added once the project receives a DOI.

For now, please cite the repository as:

```text
Llanos, D. R. Open Bitcoin Metrics: Reproducible Full-Node-Derived Bitcoin On-Chain Time Series 
GitHub repository, version OBM v0.1.0.
https://github.com/diegorllanos/open-bitcoin-metrics/
```

For a specific dataset release, include the release version, for example:

```text
Open Bitcoin Metrics, OBM v0.1.0.
```

## Academic paper

The project is being developed alongside a data descriptor manuscript tentatively titled
"Open Bitcoin Metrics: A Reproducible Full-Node Dataset of Bitcoin On-Chain Time Series for 
Economic Research".

The intended contribution of the paper, that is not yet publicly available, is to document the 
dataset, metric definitions, reconstruction algorithms, validation procedures, and usage notes. We
will update this information as soon as the paper becomes available. 

## License

- Code: MIT License.
- Data and documentation: Creative Commons Attribution 4.0 International, CC BY 4.0.

See the corresponding `LICENSE` files in the `data/` and `scripts/` directories.

## Contact

Maintainer:

```text
Prof. Diego R. Llanos, diego.llanos@uva.es
Department of Computer Science
University of Valladolid, Spain
```

## Project status

OBM is under active development. The goal is to build a reliable set of robust, well-documented, reproducible Bitcoin time series, and later expanding toward more complex metrics.
