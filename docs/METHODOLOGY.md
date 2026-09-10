# Methodology

This document describes the full technical procedure implemented in `ops_pipeline_auto.py`.
The governing principle:

> **LLM plans → Python computes → LLM interprets → Report engine communicates**

The LLM never trains models or calculates metrics. It selects methodology (Stage 1)
and interprets computed evidence (Stage 2). All numbers come from the local engine.

## Stage 0 — Dataset Profiling (`profile_dataframe`)

1. **Ingestion** — `load_csv` reads the CSV; column names normalized to `snake_case`.
   Big-mode (env `OPS_BIGMODE_FILE_MB` / `OPS_BIGMODE_COL_THRESHOLD`) samples rows and
   keeps the top numeric/categorical columns while preserving the full column list in metadata.
2. **Profile** — shape, per-column dtype/missingness/`n_unique`, `describe()` for numerics,
   timestamp detection (`detect_timestamp`: name hints + `pd.to_datetime` parse rate > 0.8),
   timestamp range, candidate ID columns, `is_time_series` flag.
3. Artifact: `profile.json`. This profile — not raw rows — is what the LLM sees.

## Stage 1 — LLM Data Science Planner

Input: dataset profile + `METHOD_CATALOG` + optional `--target` hint.
Output: declarative JSON plan with keys `cleaning`, `missing_strategy`, `resampling`,
`resample_rule`, `feature_engineering`, `analyses`, `supervised`, `supervised_target`,
`visualizations`, `notes`.

The planner reasons about, within catalog bounds:

```
dataset understanding → preprocessing decisions → EDA/statistical-method selection
→ problem-type identification → supervised/unsupervised decision → algorithm selection
→ evaluation strategy → visualization strategy → structured plan
```

- **Offline mode** (`off`): `build_default_plan` — time-series profiles get
  correlation + anomaly + forecasting with time features/lags/rolling stats;
  wide numeric profiles get correlation + clustering + anomaly; `--target` enables supervised.
- **API mode**: `gemini_api_generate` POSTs the prompt to `generativelanguage.googleapis.com`,
  then `extract_json_object` pulls the JSON object from free text.
- **Browser mode**: `gemini_browser_generate` (Selenium) pastes the prompt into the web UI
  and reads back body text; experimental, falls back on any failure.
- Any LLM failure → validated default plan with a logged warning (`fallback-offline`).

### Plan validation (`validate_plan`)

Per-field allow-list checking against `METHOD_CATALOG`; unknown keys ignored with warnings;
malformed values fall back to `DEFAULT_PLAN` entries. There is deliberately **no `exec`/`eval`**
of LLM content — the plan only toggles explicitly implemented code paths.

## Execution Layer (deterministic Python/ML)

```
validated plan → cleaning → feature engineering → analyses → visualizations
```

- **Cleaning** (`clean_dataframe`): dedupe, missing strategy (`median_mode` / `ffill_bfill` / `drop`),
  optional IQR clipping.
- **Resampling**: plan field reserved; time-series normalization currently handled via
  sorted time features rather than grid resampling (see Limitations).
- **Feature engineering** (`engineer_features`): hour/day-of-week/month, lag-1 and
  rolling-mean-3 for up to 3 numeric columns when a timestamp exists.
- **Correlation** (`run_correlation`): Pearson matrix capped by `OPS_MAX_CORR_COLS`; top-10
  absolute pairs recorded; matrix saved to `tables/correlation.csv`.
- **Clustering** (`run_clustering`): StandardScaler + KMeans (k heuristic, capped fit rows via
  `OPS_CLUSTER_MAX_FIT_ROWS`); skipped without scikit-learn or <10 rows / <2 numeric cols.
- **Anomaly detection** (`run_anomaly`): IsolationForest (5% contamination), z-score fallback
  without sklearn.
- **Forecasting** (`run_forecast`): naive last-value backtest (80/20 split) reporting MAE/RMSE.
  This is a baseline sanity check, not a production forecaster.
- **Supervised** (`run_supervised`, only with `--target` or plan target): preprocessing
  ColumnTransformer (StandardScaler + OneHotEncoder) + Logistic/Linear or RandomForest,
  75/25 split, accuracy/F1 (classification) or RMSE/R² (regression); pipeline saved via joblib
  to `models/supervised_pipeline.joblib` when available.
- **Visualization** (`make_plots`, matplotlib Agg): histograms, correlation heatmap,
  time series, cluster scatter, forecast summary — only what the plan requests and data supports.

## Stage 2 — LLM Result Interpreter

Input: compact computed-results JSON (metrics, statuses, profile shape) — never raw row data.
Output: `executive_summary`, `key_findings`, `recommendations`, `limitations`.

- **Offline**: `deterministic_sections` templates sentences directly from computed values.
- **API/browser**: prompt instructs the model to use only provided numbers; response parsed
  with `extract_json_object`; missing `key_findings` triggers the offline fallback.
- Artifact: `gemini_stage2_sections.json` with a `source` field (`offline-template`,
  `gemini-api`, `gemini-browser`, `fallback-offline`) so readers know what wrote the narrative.

## Report Engine

`build_latex` assembles executive summary + dataset profile + plan + verbatim computed
results + Stage-2 narrative + figure includes + reproducibility note into
`reports/<RUN_ID>_report.tex`. `compile_pdf` runs `pdflatex` best-effort; the `.tex`
is always produced, the `.pdf` only when a LaTeX engine exists. Report depth is dynamic:
sections render whatever analyses actually ran (skipped modules appear as `skipped` with reasons).

## Limitations

- Resampling grid aggregation is plan-reserved but not yet a distinct transform step.
- Forecasting is intentionally naive; use `prophet`/`statsmodels` paths as future extensions.
- Supervised task-type inference is heuristic (`nunique <= 20` + method name).
- LLM narrative quality depends on mode; offline template is factual but terse.
