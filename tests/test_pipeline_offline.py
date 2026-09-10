"""Offline end-to-end + fallback tests. No API key, no browser required."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ops_pipeline_auto as pipe


def _toy_csv(tmp_path: Path) -> Path:
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=60, freq="h"),
            "temperature": [20 + (i % 10) * 0.5 for i in range(60)],
            "pressure": [100 + (i % 5) for i in range(60)],
        }
    )
    p = tmp_path / "toy.csv"
    df.to_csv(p, index=False)
    return p


def test_offline_run_produces_artifacts(tmp_path):
    csv = _toy_csv(tmp_path)
    rc = pipe.main(
        [
            str(csv),
            "--out",
            str(tmp_path / "outputs"),
            "--gemini-mode",
            "off",
            "--run-id",
            "t1",
            "--no-plots",
        ]
    )
    assert rc == 0
    run = tmp_path / "outputs" / "t1"
    for name in (
        "profile.json",
        "gemini_plan.json",
        "gemini_stage2_sections.json",
        "manifest.json",
        "pipeline.log",
    ):
        assert (run / name).is_file(), name
    tex = run / "reports" / "t1_report.tex"
    assert tex.is_file() and "Executive Summary" in tex.read_text(encoding="utf-8")
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["plan_source"] == "offline"


def test_api_failure_falls_back_offline(tmp_path):
    csv = _toy_csv(tmp_path)
    with patch.object(pipe, "gemini_api_generate", side_effect=RuntimeError("no net")):
        rc = pipe.main(
            [
                str(csv),
                "--out",
                str(tmp_path / "outputs"),
                "--gemini-mode",
                "api",
                "--run-id",
                "t2",
                "--no-plots",
            ]
        )
    assert rc == 0
    plan = json.loads(
        (tmp_path / "outputs" / "t2" / "gemini_plan.json").read_text(encoding="utf-8")
    )
    assert plan["source"] == "fallback-offline"


def test_malformed_llm_json_falls_back(tmp_path):
    csv = _toy_csv(tmp_path)
    with patch.object(pipe, "gemini_api_generate", return_value="not json at all {{{"):
        rc = pipe.main(
            [
                str(csv),
                "--out",
                str(tmp_path / "outputs"),
                "--gemini-mode",
                "api",
                "--run-id",
                "t3",
                "--no-plots",
            ]
        )
    assert rc == 0
    plan = json.loads(
        (tmp_path / "outputs" / "t3" / "gemini_plan.json").read_text(encoding="utf-8")
    )
    assert plan["source"] == "fallback-offline"


def test_missing_csv_returns_error(tmp_path):
    rc = pipe.main(
        [
            str(tmp_path / "nope.csv"),
            "--out",
            str(tmp_path / "o"),
            "--gemini-mode",
            "off",
        ]
    )
    assert rc == 2
