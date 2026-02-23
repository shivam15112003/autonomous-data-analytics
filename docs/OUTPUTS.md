# Outputs

A typical run creates:

```
outputs/
  <RUN_ID>/
    pipeline.log
    profile.json
    gemini_plan.json
    gemini_stage2_sections.json          (only if Stage-2 ran successfully)
    manifest.json                        (paths to key artifacts)
    reports/
      <RUN_ID>_report.tex
      <RUN_ID>_report.pdf                (only if LaTeX is installed)
    figures/                             (if enabled by plan)
    tables/                              (csv/tex summaries)
    models/                              (if supervised modeling enabled)
    saved_pipelines/                     (optional: reusable supervised pipelines)
```

`manifest.json` is the best automation hook: it tells you where the report and key run artifacts are located.
