# Autonomous Ops Analytics

A recruiter-friendly, production-lean **autonomous data analysis pipeline** repository scaffold.

This repo is set up for a single entry-point script you will add yourself:

- **Place your pipeline script at:** `ops_pipeline_auto.py`
  - If your file is currently named `ops_pipeline_auto4.py`, just rename it to `ops_pipeline_auto.py`.

The pipeline is designed to take a CSV and produce an operations-style analytics package:
- dataset profiling
- plots & tables
- optional anomaly detection / clustering / forecasting / supervised modeling
- **LaTeX report** and best-effort **PDF** build
- optional Gemini-assisted planning + narrative

---

## Quickstart

### 1) Create a venv and install core dependencies
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
```

### 2) Run (Gemini OFF / deterministic)
```bash
python ops_pipeline_auto.py path/to/data.csv --out outputs --gemini-mode off
```

### 3) Optional: install advanced / heavy dependencies
```bash
pip install -r requirements-optional.txt
```

---

## Gemini usage

### API mode
Create a key file:
```bash
cp gemini_api_key.txt.example gemini_api_key.txt
# edit gemini_api_key.txt and paste your key
python ops_pipeline_auto.py path/to/data.csv --out outputs --gemini-mode api
```

Or use env vars:
```bash
export GEMINI_API_KEY="YOUR_KEY"
python ops_pipeline_auto.py path/to/data.csv --out outputs --gemini-mode api
```

### Browser mode
Browser mode uses Selenium to interact with Gemini UI. You’ll need:
- Chrome
- chromedriver on PATH
- `selenium` installed (`requirements-optional.txt`)

```bash
python ops_pipeline_auto.py path/to/data.csv --out outputs --gemini-mode browser
```

---

## Outputs

Each run creates a timestamped folder under `--out` (default `outputs/`), typically including:
- `profile.json`
- `gemini_plan.json`
- `gemini_stage2_sections.json` (if Stage-2 succeeded)
- `reports/<run>_report.tex`
- `reports/<run>_report.pdf` (if LaTeX engine installed)
- `pipeline.log`
- `manifest.json` (paths to key artifacts)

See: `docs/OUTPUTS.md`

---

## Repository structure

```
.
├── ops_pipeline_auto.py              # (you add this)
├── requirements.txt
├── requirements-optional.txt
├── gemini_api_key.txt.example
├── docs/
│   ├── METHODOLOGY.md
│   ├── CONFIG.md
│   ├── OUTPUTS.md
│   └── ARCHITECTURE.md
├── examples/
│   ├── run_offline.sh
│   ├── run_gemini_api.sh
│   └── run_gemini_browser.sh
└── .github/workflows/ci.yml
```

---

## License
MIT — see `LICENSE`.
