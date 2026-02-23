#!/usr/bin/env bash
set -euo pipefail
python ops_pipeline_auto.py ./data.csv --out outputs --gemini-mode browser
