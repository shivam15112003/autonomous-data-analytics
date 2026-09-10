"""Tests for Stage-1 plan validation. No API key, no browser required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops_pipeline_auto import DEFAULT_PLAN, validate_plan


def test_valid_plan_passes_through():
    raw = {
        "cleaning": ["drop_duplicates", "iqr_clip"],
        "missing_strategy": "ffill_bfill",
        "resampling": "disabled",
        "resample_rule": "1h",
        "feature_engineering": ["time_features"],
        "analyses": ["correlation", "anomaly_detection"],
        "supervised": "disabled",
        "supervised_target": None,
        "visualizations": ["histograms"],
        "notes": "test",
    }
    plan, warnings = validate_plan(raw)
    assert plan["analyses"] == ["correlation", "anomaly_detection"]
    assert warnings == []


def test_unsupported_values_dropped_with_warnings():
    raw = {
        "analyses": ["correlation", "mind_reading"],
        "supervised": "gpt42",
        "cleaning": "not-a-list",
    }
    plan, warnings = validate_plan(raw)
    assert plan["analyses"] == ["correlation"]
    assert plan["supervised"] == "disabled"
    assert plan["cleaning"] == DEFAULT_PLAN["cleaning"]
    assert len(warnings) >= 3


def test_non_dict_falls_back_to_default():
    plan, warnings = validate_plan("DROP TABLE")  # type: ignore[arg-type]
    assert plan == DEFAULT_PLAN
    assert warnings


def test_unknown_keys_ignored_and_reported():
    plan, warnings = validate_plan({"analyses": ["correlation"], "exec": "rm -rf /"})
    assert "exec" not in plan
    assert any("exec" in w for w in warnings)


def test_no_exec_or_eval_in_validation():
    import inspect
    import ops_pipeline_auto as m

    src = inspect.getsource(m.validate_plan) + inspect.getsource(m.extract_json_object)
    assert "exec(" not in src and "eval(" not in src
