# Open Bitcoin Metrics (OBM)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21156871.svg)](https://doi.org/10.5281/zenodo.21156871)
[![arXiv](https://img.shields.io/badge/arXiv-2607.03124-b31b1b.svg)](https://arxiv.org/abs/2607.03124)
[![Code: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE)
[![Data: CC BY 4.0](https://img.shields.io/badge/Data-CC%20BY%204.0-lightgrey.svg)](DATA_LICENSE)

**Open Bitcoin Metrics (OBM)** is an open-data project that provides transparent, reproducible, full-node-derived Bitcoin on-chain time series for economic, financial, and econometric research.

The project aims to make specialized Bitcoin metrics easier to access, audit, cite, reproduce, and compare. OBM follows Bitcoin's "do not trust, verify" principle by making the metric-generation process inspectable and rerunnable instead of requiring users to rely on opaque data pipelines.

Each metric is accompanied by:

- a CSV time series;
- a Python script that generates the series;
- a stable series identifier;
- an explicit definition and measurement unit;
- documentation of the algorithm used to compute the metric;
- validation notes and known limitations;
- metadata fields intended to support reproducibility and academic use.

The archived dataset release is **OBM v0.1.0** and is available on Zenodo:

```text
https://doi.org/10.5281/zenodo.21156871
```

The companion paper is available on arXiv:

```text
https://arxiv.org/abs/2607.03124
```

## Motivation

Bitcoin research increasingly relies on on-chain indicators to study network activity, monetary issuance, transaction demand, fee-market dynamics, miner incentives, coin-age behavior, UTXO-state evolution, and long-run monetary properties.

However, many commonly used Bitcoin metrics are dispersed across commercial platforms, blockchain explorers, public dashboards, and proprietary APIs. Even when charts or downloads are publicly visible, definitions, timestamp conventions, treatment of edge cases, smoothing choices, entity-adjustment rules, and reconstruction algorithms are often only partially documented.

OBM addresses this reproducibility gap by providing an open, documented, full-node-derived baseline. The objective is not to replace commercial data providers, which often offer broad coverage, refined interfaces, higher-frequency data, entity-adjusted indicators, and market analytics. Rather, OBM provides selected Bitcoin time series reconstructed through explicit procedures, distributed with stable names, clear units, validation checks, and documented limitations.

## Current release

The current release is:

```text
OBM v0.1.0
```

This release contains **23 daily Bitcoin on-chain metrics** covering:

- block production;
- block-space usage;
- transaction counts;
- monetary issuance and supply;
- transaction fees and miner revenue;
- mining difficulty and estimated hashrate;
- Bitcoin Days Destroyed;
- dormancy and liveliness;
- UTXO counts;
- spent output value;
- UTXO-age and threshold-based spent-value indicators.

The metrics are generated using three complementary approaches:

| Type | Description |
|---|---|
| Primary | Computed directly from a locally verified Bitcoin Core full node. |
| Indexer-exported | Exported from aggregates produced by the OBM spent-output indexer, which reconstructs previous outputs over the blockchain. |
| Derived | Computed as deterministic transformations of already generated OBM series, without querying Bitcoin Core directly. |

## Available metrics

| Series identifier and display name | Description | Frequency | Unit | Type |
|---|---|---|---|---|
| `obm_block_count_daily`: Daily Bitcoin block count | Daily number of Bitcoin blocks assigned to each UTC date | Daily | Blocks | Primary |
| `obm_block_weight_wu_daily`: Daily block weight in weight units | Total daily block weight of all blocks assigned to each UTC date | Daily | WU | Primary |
| `obm_cdd_age_band_btcxdays_daily`: Bitcoin Days Destroyed by age band | Daily Bitcoin Days Destroyed decomposed by spent-output age band | Daily | BTC-days | Indexer-exported |
| `obm_cdd_btcxdays_daily`: Bitcoin Days Destroyed | Daily Bitcoin Days Destroyed from spent outputs | Daily | BTC-days | Indexer-exported |
| `obm_cdd_per_supply_days_daily`: Bitcoin Days Destroyed per unit of supply | Supply-normalized Bitcoin Days Destroyed | Daily | Days | Derived |
| `obm_difficulty_eod_daily`: End-of-day Bitcoin mining difficulty | Mining difficulty of the highest-height block assigned to each UTC date | Daily | Difficulty | Primary |
| `obm_dormancy_days_daily`: Daily dormancy | Value-weighted average age of outputs spent each day | Daily | Days | Indexer-exported |
| `obm_est7d_hashrate_ehs_daily`: Estimated 7-day network hashrate | Estimated network hashrate using a trailing 7-day UTC window | Daily | EH/s | Primary |
| `obm_fee_share_revenue_ratio_daily`: Fees as share of miner revenue | Daily transaction fees divided by miner revenue | Daily | Ratio | Derived |
| `obm_fees_btc_daily`: Daily transaction fees in BTC | Total daily transaction fees paid by non-coinbase transactions | Daily | BTC | Indexer-exported |
| `obm_issuance_btc_daily`: Daily Bitcoin issuance | Realized daily Bitcoin issuance in BTC | Daily | BTC | Indexer-exported |
| `obm_liveliness_ratio_daily`: Daily liveliness ratio | Cumulative coin-days destroyed relative to cumulative coin-days created | Daily | Ratio | Derived |
| `obm_miner_revenue_btc_daily`: Daily miner revenue in BTC | Daily miner revenue from coinbase outputs, including issuance and fees | Daily | BTC | Indexer-exported |
| `obm_raw_output_value_btc_daily`: Daily raw output value in BTC | Total BTC value of non-coinbase transaction outputs | Daily | BTC | Primary |
| `obm_spent_output_count_daily`: Daily spent output count | Number of previous outputs spent by non-coinbase transaction inputs | Daily | Outputs | Indexer-exported |
| `obm_spent_value_age_band_btc_daily`: Spent output value by age band in BTC | Daily spent output value decomposed by spent-output age band | Daily | BTC | Indexer-exported |
| `obm_spent_value_btc_daily`: Daily spent output value in BTC | Total BTC value of previous outputs spent each day | Daily | BTC | Indexer-exported |
| `obm_spent_value_ge155d_btc_daily`: Spent output value aged at least 155 days | Daily BTC value of spent outputs aged at least 155 days | Daily | BTC | Indexer-exported |
| `obm_spent_value_ge365d_btc_daily`: Spent output value aged at least 365 days | Daily BTC value of spent outputs aged at least 365 days | Daily | BTC | Indexer-exported |
| `obm_spent_value_lt155d_btc_daily`: Spent output value younger than 155 days | Daily BTC value of spent outputs aged less than 155 days | Daily | BTC | Derived |
| `obm_supply_btc_daily`: Bitcoin supply | End-of-day accumulated Bitcoin supply since genesis | Daily | BTC | Derived |
| `obm_tx_count_daily`: Daily Bitcoin transaction count | Daily number of Bitcoin transactions confirmed on-chain | Daily | Transactions | Primary |
| `obm_utxo_eod_count_daily`: End-of-day UTXO count | Number of spendable UTXOs after the highest-height block assigned to each UTC date | Daily | Outputs | Primary |

## Data philosophy

OBM follows six principles.

### 1. Primary-source derivation

Metrics are reconstructed from Bitcoin blockchain data obtained through a Bitcoin Core full node whenever possible.

### 2. Transparent definitions

Each variable is associated with an explicit definition, a stable series identifier, a measurement unit, and a documented computational procedure.

### 3. Econometric usability

Series are distributed at regular time intervals, initially daily, using clear timestamp conventions, aggregation rules, units, and metadata.

### 4. Versioned reproducibility

Scripts, outputs, documentation, and data releases are archived and versioned. Dataset releases use explicit release labels, for example:

```text
OBM v0.1.0
```

### 5. Validation

Selected metrics are checked using internal identities, consistency tests, and diagnostic comparisons with independent public sources.

### 6. Verification-oriented openness

Users are not required to treat OBM as an authority. They can inspect, rerun, compare, and modify the code that generates the metrics.

## Data-generation pipeline

The OBM pipeline transforms primary Bitcoin blockchain data into regular, documented, econometric-ready time series.

The general workflow is:

1. synchronize and maintain a Bitcoin Core full node;
2. extract block-level and transaction-level information from the validated main chain;
3. reconstruct previous outputs where required;
4. store reusable spent-output and block-level aggregates in a persistent indexer database;
5. export metric-specific daily series from the node scan, the indexer database, or existing OBM CSV files;
6. produce monthly versions where appropriate, using metric-specific aggregation rules;
7. validate outputs using internal identities and diagnostic comparisons;
8. publish updated files, scripts, metadata, and documentation.

The spent-output indexer is used for metrics requiring previous-output reconstruction, including transaction fees, realized issuance, miner revenue, spent value, Bitcoin Days Destroyed, dormancy, and UTXO-age indicators.

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
obm_cdd_btcxdays_daily
```

The `obm_` prefix identifies the Open Bitcoin Metrics dataset and reduces ambiguity when OBM series are merged with external macro-financial variables.

## Repository structure

The repository is organized around metric-level directories and shared tools:

```text
open-bitcoin-metrics/
    metrics/
       <metric_name>/
          compute_<metric_name>.py
          <metric_name>.csv
          <metric_name>.png
          README.md
       DATA_LICENSE
       LICENSE
    tools/
       auxiliar-scripts/
          plot_obm_csv.py
          README.md
       spent_output_indexer/
          obm_spent_output_indexer.py
          README.md
    CITATION.cff
    README.md
```

Each metric directory contains the files needed to understand, regenerate, and inspect the corresponding series. Metric-level README files provide the definition, interpretation, data format, script usage, validation notes, known limitations, citation guidance, and license information for each series.

## Reproducibility requirements

OBM scripts assume some combination of the following requirements, depending on the metric:

- Python 3;
- a synchronized Bitcoin Core full node;
- access to the Bitcoin Core JSON-RPC interface;
- a non-pruned node with `txindex=1` for full historical reconstruction;
- a Linux environment for scheduled execution;
- the OBM spent-output indexer database for metrics requiring previous-output reconstruction;
- existing OBM CSV files for derived metrics;
- optional plotting libraries, such as `matplotlib`, when plots are requested.

Not every metric requires direct Bitcoin Core access. Derived metrics such as `obm_fee_share_revenue_ratio_daily`, `obm_cdd_per_supply_days_daily`, `obm_liveliness_ratio_daily`, `obm_supply_btc_daily`, and `obm_spent_value_lt155d_btc_daily` are computed from already generated OBM series.

## Example usage

The exact command-line parameters are metric-specific. See the README file inside each metric directory for full instructions.

A typical primary metric can be generated as follows:

```bash
python3 metrics/obm_tx_count_daily/compute_obm_tx_count_daily.py \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output metrics/obm_tx_count_daily/obm_tx_count_daily.csv \
  --release_version "OBM v0.1.0" \
  --plot \
  --plot_output metrics/obm_tx_count_daily/obm_tx_count_daily.png
```

A derived metric can be generated from existing OBM CSV files. For example:

```bash
python3 metrics/obm_cdd_per_supply_days_daily/compute_obm_cdd_per_supply_days_daily.py \
  metrics/obm_cdd_btcxdays_daily/obm_cdd_btcxdays_daily.csv \
  metrics/obm_supply_btc_daily/obm_supply_btc_daily.csv \
  --start_date 2024-01-01 \
  --end_date 2024-01-31 \
  --output metrics/obm_cdd_per_supply_days_daily/obm_cdd_per_supply_days_daily.csv \
  --plot \
  --plot_output metrics/obm_cdd_per_supply_days_daily/obm_cdd_per_supply_days_daily.png
```

To plot any OBM-compatible CSV file:

```bash
python3 tools/auxiliar-scripts/plot_obm_csv.py \
  metrics/obm_tx_count_daily/obm_tx_count_daily.csv \
  --output metrics/obm_tx_count_daily/obm_tx_count_daily.png
```

## Validation

Validation is metric-specific, but OBM generally relies on three types of checks:

1. **Internal consistency checks**, such as missing dates, duplicate dates, negative values, inconsistent totals, invalid units, or inconsistent release labels.
2. **Reproducibility checks**, ensuring that scripts can regenerate the published series from the documented inputs.
3. **External diagnostic comparisons**, when comparable public series are available.

External comparisons are diagnostic rather than definitive. Data providers may differ in timestamp conventions, treatment of chain reorganizations, entity-adjustment heuristics, smoothing choices, or metric definitions.

## Known limitations

OBM metrics should be interpreted carefully.

- On-chain transactions do not map one-to-one to users.
- On-chain transactions do not map one-to-one to economically distinct payments.
- Raw transaction-value and spent-value metrics can include self-transfers, change outputs, exchange activity, custodial wallet management, batching, and wallet consolidation.
- Address-based and entity-adjusted metrics are not included unless explicitly documented.
- USD-denominated metrics require external price data and are not purely full-node-derived.
- Daily aggregation depends on timestamp conventions.
- Bitcoin block timestamps are not strictly monotonic.
- Some early historical edge cases require explicit conventions, including duplicate coinbase transaction identifiers and apparent negative spent-output ages caused by timestamp ordering.
- Rolling repository updates may be revised if bugs, edge cases, or definitional improvements are identified.

These limitations are documented to prevent overinterpretation and to make empirical use of the series more transparent.

## Suggested citation

Please cite both the archived dataset release and the companion paper.

### Dataset

```text
Llanos, D. R. (2026). Open Bitcoin Metrics (OBM): Reproducible Full-Node Bitcoin On-Chain Time Series, Version 0.1.0. Zenodo. https://doi.org/10.5281/zenodo.21156871
```

### Companion paper

```text
Llanos, D. R. (2026). Open Bitcoin Metrics: Verifiable Full-Node-Derived Bitcoin Time Series for Economic Research. arXiv:2607.03124v1. https://arxiv.org/abs/2607.03124
```

### BibTeX

```bibtex
@dataset{llanos_obm_2026,
  author       = {Llanos, Diego R.},
  title        = {Open Bitcoin Metrics (OBM): Reproducible Full-Node Bitcoin On-Chain Time Series, Version 0.1.0},
  year         = {2026},
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.21156871},
  url          = {https://doi.org/10.5281/zenodo.21156871}
}

@misc{llanos_obm_arxiv_2026,
  author       = {Llanos, Diego R.},
  title        = {Open Bitcoin Metrics: Verifiable Full-Node-Derived Bitcoin Time Series for Economic Research},
  year         = {2026},
  eprint       = {2607.03124},
  archivePrefix = {arXiv},
  primaryClass = {cs.CE},
  url          = {https://arxiv.org/abs/2607.03124}
}
```

## Academic paper

The companion paper documents the dataset, metric definitions, reconstruction algorithms, validation procedures, usage notes, limitations, and public comparators:

```text
Open Bitcoin Metrics: Verifiable Full-Node-Derived Bitcoin Time Series for Economic Research
arXiv:2607.03124v1
https://arxiv.org/abs/2607.03124
```

## License

- Code: MIT License.
- Data and documentation: Creative Commons Attribution 4.0 International, CC BY 4.0.

See the corresponding license files in the repository.

## Contact

Maintainer:

```text
Prof. Diego R. Llanos
diego.llanos@uva.es
Department of Computer Science
University of Valladolid, Spain
```

## Project status

OBM is under active maintenance. The current public release is **OBM v0.1.0**, archived on Zenodo and documented in the companion arXiv paper. The repository provides the live location for code, documentation, metric-level README files, plots, and rolling updates.
