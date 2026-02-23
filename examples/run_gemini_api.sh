#!/usr/bin/env bash
set -euo pipefail
# Put your key in gemini_api_key.txt OR export GEMINI_API_KEY
python ops_pipeline_auto.py ./data.csv --out outputs --gemini-mode api --gemini-model gemini-2.5-flash
