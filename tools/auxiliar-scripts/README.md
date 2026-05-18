# OBM Plotting Utilities

This directory contains auxiliary plotting scripts for Open Bitcoin Metrics (OBM) CSV files. These scripts do not compute, transform, or validate OBM metrics for release. Their purpose is to generate publication- or inspection-oriented PNG plots from already generated OBM-compatible CSV files.

The current plotting utilities are:

```text
plot_obm_csv.py
plot_obm_cdd_age_band_btcxdays_daily.py
plot_obm_spent_value_age_band_btc_daily.py
```

## Requirements

All scripts require Python 3. Plot generation requires `matplotlib`:

```bash
python3 -m pip install matplotlib
```

The scripts use only standard-library modules for CSV parsing and validation, apart from `matplotlib` for plotting.

## 1. Generic scalar-series plotter

### Script

```text
plot_obm_csv.py
```

### Purpose

This is the general OBM plotting utility. It reads a scalar OBM CSV file using the standard schema:

```text
date,series_id,value,unit,frequency,release_version
```

and plots the `value` column against `date`.

It is suitable for ordinary one-value-per-date OBM series, such as:

```text
obm_tx_count_daily
obm_block_count_daily
obm_fees_btc_daily
obm_supply_btc_daily
obm_utxo_eod_count_daily
```

It is not intended for wide, multi-column age-band tables.

### Input expectations

The input CSV must contain at least:

```text
date
value
unit
frequency
```

The `series_id` column is optional but recommended. If present, the script expects at most one distinct `series_id` in the file.

The script checks that:

- the date column can be parsed as `YYYY-MM-DD`;
- the value column can be parsed as numeric data;
- there is a single unit in the file;
- there is a single frequency in the file;
- there is at most one series identifier.

Rows are sorted chronologically before plotting.

### Example usage

```bash
python3 plot_obm_csv.py \
  data/daily/obm_tx_count_daily.csv \
  --output figures/obm_tx_count_daily.png
```

If `--output` is omitted, the script writes:

```text
plot.png
```

## 2. CDD age-band stacked-area plotter

### Script

```text
plot_obm_cdd_age_band_btcxdays_daily.py
```

### Purpose

This script generates a stacked-area plot for:

```text
obm_cdd_age_band_btcxdays_daily
```

The input is a wide daily CSV file in which each row corresponds to one UTC date and each age-band column reports the Bitcoin Days Destroyed contributed by spent outputs in that age band.

The filled areas in the plot represent the contribution of each age band to total daily Bitcoin Days Destroyed.

### Input expectations

The script expects the following series-level metadata:

```text
series_id = obm_cdd_age_band_btcxdays_daily
unit = BTC-days
frequency = daily
```

It also expects the following age-band columns:

```text
cdd_0d_1d_btcxdays
cdd_1d_1w_btcxdays
cdd_1w_1m_btcxdays
cdd_1m_3m_btcxdays
cdd_3m_6m_btcxdays
cdd_6m_1y_btcxdays
cdd_1y_2y_btcxdays
cdd_2y_3y_btcxdays
cdd_3y_5y_btcxdays
cdd_5y_7y_btcxdays
cdd_7y_10y_btcxdays
cdd_10y_plus_btcxdays
```

The script checks that:

- all required columns are present;
- dates are valid and non-duplicated;
- the `series_id`, `unit`, and `frequency` fields match the expected values;
- each age-band value is present, numeric, and non-negative.

Rows are sorted chronologically before plotting.

### Example usage

```bash
python3 plot_obm_cdd_age_band_btcxdays_daily.py \
  data/daily/obm_cdd_age_band_btcxdays_daily.csv \
  --output figures/obm_cdd_age_band_btcxdays_daily.png
```

The `--output` argument is mandatory.

## 3. Spent-value age-band stacked-area plotter

### Script

```text
plot_obm_spent_value_age_band_btc_daily.py
```

### Purpose

This script generates a stacked-area plot for:

```text
obm_spent_value_age_band_btc_daily
```

The input is a wide daily CSV file in which each row corresponds to one UTC date and each age-band column reports the BTC value of outputs spent on that date whose age falls within the corresponding band.

The filled areas in the plot represent the contribution of each age band to total daily spent output value.

### Input expectations

The script expects the following series-level metadata:

```text
series_id = obm_spent_value_age_band_btc_daily
unit = BTC
frequency = daily
```

It also expects the following age-band columns:

```text
spent_value_0d_1d_btc
spent_value_1d_1w_btc
spent_value_1w_1m_btc
spent_value_1m_3m_btc
spent_value_3m_6m_btc
spent_value_6m_1y_btc
spent_value_1y_2y_btc
spent_value_2y_3y_btc
spent_value_3y_5y_btc
spent_value_5y_7y_btc
spent_value_7y_10y_btc
spent_value_10y_plus_btc
```

The script checks that:

- all required columns are present;
- dates are valid and non-duplicated;
- the `series_id`, `unit`, and `frequency` fields match the expected values;
- each age-band value is present, numeric, and non-negative.

Rows are sorted chronologically before plotting.

### Example usage

```bash
python3 plot_obm_spent_value_age_band_btc_daily.py \
  data/daily/obm_spent_value_age_band_btc_daily.csv \
  --output figures/obm_spent_value_age_band_btc_daily.png
```

The `--output` argument is mandatory.

## Choosing the right plotting script

| Input file type | Recommended script |
|---|---|
| Standard scalar OBM CSV with one `value` column | `plot_obm_csv.py` |
| Wide CDD age-band CSV | `plot_obm_cdd_age_band_btcxdays_daily.py` |
| Wide spent-value age-band CSV | `plot_obm_spent_value_age_band_btc_daily.py` |

## Notes

The plotting scripts are intentionally separate from metric-computation scripts. This keeps the OBM workflow clear:

```text
compute or export metric -> write CSV -> generate plot
```

Plots are convenience artifacts for inspection, documentation, and communication. The canonical dataset artifact is the CSV time series.
