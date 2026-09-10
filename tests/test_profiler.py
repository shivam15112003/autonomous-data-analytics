"""Tests for dataset profiling. No API key, no browser required."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops_pipeline_auto import normalize_columns, profile_dataframe, snake_case


def test_snake_case():
    assert snake_case("Total Pressure (psi)") == "total_pressure_psi"
    assert snake_case("  TIMESTAMP ") == "timestamp"


def test_normalize_columns():
    df = pd.DataFrame({"Total Pressure": [1.0], "STATUS": ["ok"]})
    out, mapping = normalize_columns(df)
    assert list(out.columns) == ["total_pressure", "status"]
    assert mapping["Total Pressure"] == "total_pressure"


def test_profile_basic():
    df = pd.DataFrame({"a": [1.0, 2.0, None], "b": ["x", "y", "x"]})
    df, _ = normalize_columns(df)
    profile = profile_dataframe(df)
    assert profile["shape"] == [3, 2]
    assert profile["n_numeric"] == 1
    by_name = {c["name"]: c for c in profile["columns"]}
    assert by_name["a"]["missing"] == 1
    assert by_name["b"]["n_unique"] == 2


def test_profile_detects_timestamp():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=10, freq="h"),
            "v": range(10),
        }
    )
    profile = profile_dataframe(df)
    assert profile["is_time_series"] is True
    assert profile["timestamp_column"] == "timestamp"
    assert profile["timestamp_range"] is not None
