# Sample Demonstration

A lightweight, fully synthetic demo — no private data. The dataset mimics sensor
readings (`temperature`, `pressure`, `vibration`, `status`) with a binary `fault` label.

## Run it

```bash
python ops_pipeline_auto.py sample/sample_data.csv --out outputs --gemini-mode off --target fault
```

No API key, no browser, no LaTeX required (PDF builds only if `pdflatex` exists;
the `.tex` report is always generated).

## What is committed here

- `sample_data.csv` — 200-row synthetic input (missing values included on purpose)
- `sample_outputs/` — curated artifacts from an offline run (`--target fault`):
  - `profile.json`, `gemini_plan.json`, `gemini_stage2_sections.json`, `manifest.json`, `pipeline.log`
  - `tables/correlation.csv`
  - `figures/` — histograms, time series, forecast summary
  - `reports/sample_run_report.tex` and `sample_run_report.pdf`

## Headline results (computed, offline mode)

- Strongest association: `temperature_rollmean3` vs `temperature_lag1` (|r| = 0.863, engineered features)
- Anomaly screening: 10 rows (5.0%) via IsolationForest
- Naive forecast backtest on `temperature`: RMSE = 2.26, MAE = 1.94
- Supervised classification (`fault`): accuracy = 1.0, F1-macro = 1.0

Note: the synthetic `fault` label is deliberately threshold-separable from `vibration`,
so the perfect supervised score reflects the toy data design — not a benchmark claim.
See the full metric context in `sample_outputs/gemini_stage2_sections.json`.
