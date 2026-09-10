# Outputs

A typical run creates (all paths relative to `outputs/<RUN_ID>/`):

```
outputs/
  <RUN_ID>/
    pipeline.log                    # full run log (file + console)
    profile.json                    # Stage-0 dataset profile
    gemini_plan.json                # {source, warnings, plan}
    gemini_stage2_sections.json     # {source, sections} — always written
    manifest.json                   # automation hook: run metadata + artifact paths
    reports/
      <RUN_ID>_report.tex           # always generated
      <RUN_ID>_report.pdf           # only if a LaTeX engine (pdflatex) is installed
    figures/                        # only plots requested by plan and supported by data
      histograms.png
      correlation_heatmap.png
      time_series.png
      cluster_scatter.png
      forecast_plot.png
    tables/
      correlation.csv               # only when correlation ran with >= 2 numeric cols
    models/
      supervised_pipeline.joblib    # only when supervised ran and joblib available
```

## Artifact notes

- `gemini_plan.json.source`: `offline` | `gemini-api` | `gemini-browser` | `fallback-offline`.
- `gemini_stage2_sections.json.source`: `offline-template` | `gemini-api` | `gemini-browser` | `fallback-offline`.
- Skipped analyses are recorded in the report as `skipped` with a reason (e.g. not enough
  numeric data, scikit-learn missing) — the report adapts to what actually ran.
- `manifest.json` fields: `run_id`, `created_utc`, `version`, `mode`, `plan_source`,
  `stage2_source`, `artifacts` (relative paths; `report_pdf` is `null` when LaTeX is absent).
- `outputs/` is git-ignored; curated demo copies live under `sample/sample_outputs/`.
