# Changelog

## 0.2.0
- Implemented `ops_pipeline_auto.py`: Stage-0 profiler, Stage-1 planner with
  allow-list plan validation, deterministic execution engine (cleaning, feature
  engineering, correlation, KMeans clustering, IsolationForest anomaly detection,
  naive forecast backtest, supervised classification/regression), matplotlib
  visualizations, Stage-2 interpreter with offline fallback, LaTeX/PDF report
  engine, manifest + logging.
- Three execution modes: `off` (deterministic), `api` (Gemini REST), `browser`
  (Selenium, experimental).
- Rewrote README as recruiter-friendly overview; expanded `docs/` (Methodology,
  Architecture, LLM Integration, Outputs).
- Added `sample/` synthetic demo with committed outputs including PDF report.
- Added offline test suite (`tests/`) with mocked LLM dependencies.
- Added `.gitignore` (secrets, outputs, LaTeX byproducts), MIT `LICENSE`, and CI
  (syntax check, pytest, offline smoke run).

## 0.1.0
- Initial repository scaffold (docs, examples, CI).
