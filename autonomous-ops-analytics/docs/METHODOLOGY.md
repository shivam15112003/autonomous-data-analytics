# Methodology

This project is designed as an “autonomous analyst” pipeline: it ingests a CSV, profiles + cleans it,
runs a configurable set of analytics, and produces a structured report package.

## 1) Ingestion & column normalization
- Reads the CSV and standardizes column names (snake_case) for consistent downstream processing.
- For very large / very wide CSVs, it may switch to a “big-mode” strategy:
  - reads header to capture the full column list
  - samples rows to select the most informative numeric + categorical columns
  - preserves the full standardized column list in metadata for later selection

## 2) Dataset profiling
Produces a profile artifact capturing:
- shape, column types
- missingness and basic distributions
- timestamp range (if a time column is detected)
- candidate ID columns

## 3) Plan selection (optional LLM-driven)
The pipeline can use a plan JSON to decide:
- cleaning strategies
- resampling rule + aggregation
- feature engineering methods
- which analysis methods to run (correlation, clustering, anomalies, forecasting)
- whether supervised modeling is enabled (interactive / optional)

When Gemini is enabled, the pipeline requests a plan based on:
- the dataset profile + a catalog of allowed methods
- operational context (time series vs. non-time series, missingness, column types)

If Gemini is disabled, a conservative default plan is used.

## 4) Cleaning & preprocessing
Typical steps include:
- timestamp parsing + sorting
- duplicate handling
- missing value strategies (ffill/bfill/median/mode/constant/drop)
- outlier treatment (e.g., IQR clipping)
- scaling + encoding (when ML methods are used)

## 5) Resampling (time series)
If a timestamp exists and resampling is enabled:
- time grid normalization
- aggregation (mean/median/sum/mode depending on column type)
- optional grouping by asset/unit identifiers

## 6) Feature engineering
Common time-series feature patterns:
- time-based features (hour/day-of-week/etc.)
- lags
- rolling window statistics
- differencing
- exponentially weighted stats

## 7) Analytics
Depending on the plan and installed libraries:
- correlation analysis (guard-railed for extremely wide data)
- clustering (with scaling, optional sampling for very large row counts)
- anomaly detection (e.g., Isolation Forest / LOF / One-Class SVM)
- forecasting (simple backtesting metrics)

## 8) Supervised prediction (optional, interactive)
If enabled:
- choose a target column
- infer task type (regression vs. classification)
- train + evaluate
- optionally save a full preprocessing+model pipeline for reuse
- support prediction-only runs using saved pipelines

## 9) Reporting
Produces:
- figures (plots, diagnostics)
- LaTeX tables
- LaTeX report with structured sections
- best-effort PDF compilation if a LaTeX engine is installed
- manifest.json for downstream automation
