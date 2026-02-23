# Architecture

This repo intentionally uses a **single-script** entry point (`ops_pipeline_auto.py`) to keep onboarding simple.
Internally, the pipeline typically flows like this:

1. CLI parses inputs and initializes a run directory
2. CSV ingestion + schema inference
3. Dataset profiling (lightweight summary)
4. Optional LLM plan selection (Stage 1) using only the profile + method catalog
5. Execution of plan-selected transforms and analysis modules
6. Plot/table generation
7. Optional LLM report writing (Stage 2) based on compact results + inventory
8. LaTeX assembly + best-effort PDF compilation
9. Manifest writing for automation / downstream consumption

Recommended extension points (if you later split into a package):
- `io.py`: ingestion + typing + timestamp inference
- `profile.py`: dataset profile + big-mode sampling strategy
- `analysis/*.py`: analytics modules (anomaly, clustering, forecast, supervised)
- `reporting/*.py`: LaTeX builder + figure/table helpers
- `llm/*.py`: Gemini API/browser clients + plan/section validators
