#!/usr/bin/env python3
"""Autonomous Ops Analytics — single-script entry point.

Two-stage LLM-orchestrated data science pipeline:

    LLM PLANS -> Python COMPUTES -> LLM INTERPRETS -> Report engine COMMUNICATES

Stage 0: dataset profiling (deterministic, local).
Stage 1: LLM data-science planner -> structured JSON plan -> schema validation
         -> deterministic Python/ML execution engine.
Stage 2: LLM result interpreter (evidence-grounded) -> narrative sections.
Report: dynamic LaTeX/PDF assembly from computed evidence + narrative.

Execution modes (--gemini-mode):
  off     : fully local / deterministic (default, no credentials, no browser).
  api     : Gemini API via REST (requires key in gemini_api_key.txt or env).
  browser : Selenium automation of Gemini web UI (experimental, dev only).

The LLM is the reasoning/orchestration layer. All numerical computation
(metrics, statistics, model training) is performed locally by the Python
engine. The pipeline never executes arbitrary code from the LLM; plans are
declarative JSON validated against an allow-list before execution.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path

VERSION = "0.2.0"

METHOD_CATALOG = {
    "cleaning": ["drop_duplicates", "ffill_bfill", "median_mode_fill", "iqr_clip"],
    "resampling": ["time_grid_mean", "time_grid_median", "disabled"],
    "feature_engineering": ["time_features", "lags", "rolling_stats", "disabled"],
    "analysis": ["correlation", "clustering", "anomaly_detection", "forecasting"],
    "supervised": [
        "logistic_regression",
        "random_forest_classifier",
        "linear_regression",
        "random_forest_regressor",
        "disabled",
    ],
    "visualization": [
        "histograms",
        "correlation_heatmap",
        "time_series",
        "cluster_scatter",
        "forecast_plot",
    ],
}

ALLOWED_TOP_KEYS = {
    "cleaning",
    "missing_strategy",
    "resampling",
    "resample_rule",
    "feature_engineering",
    "analyses",
    "supervised",
    "supervised_target",
    "visualizations",
    "notes",
}

DEFAULT_PLAN = {
    "cleaning": ["drop_duplicates", "median_mode_fill"],
    "missing_strategy": "median_mode",
    "resampling": "disabled",
    "resample_rule": "1h",
    "feature_engineering": ["disabled"],
    "analyses": ["correlation"],
    "supervised": "disabled",
    "supervised_target": None,
    "visualizations": ["histograms", "correlation_heatmap"],
    "notes": "Conservative offline default plan.",
}

log = logging.getLogger("ops_pipeline")


def snake_case(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip())
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return re.sub(r"_+", "_", s).strip("_").lower() or "column"


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def read_api_key(explicit: str | None = None) -> str | None:
    if explicit and Path(explicit).is_file():
        for line in (
            Path(explicit).read_text(encoding="utf-8", errors="ignore").splitlines()
        ):
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    for f in ("gemini_api_key.txt", "gemini_api_key.txt.example"):
        p = Path(f)
        if p.is_file():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "YOUR_" not in line:
                    return line
    for env in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(env, "").strip():
            return os.environ[env].strip()
    return None


def latex_escape(s: str) -> str:
    return (
        str(s)
        .replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("$", r"\$")
        .replace("#", r"\#")
        .replace("_", r"\_")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("~", r"\textasciitilde{}")
        .replace("^", r"\textasciicircum{}")
    )


def json_safe(obj):
    import math

    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    try:
        import numpy as _np

        if isinstance(obj, _np.integer):
            return int(obj)
        if isinstance(obj, _np.floating):
            f = float(obj)
            return f if math.isfinite(f) else None
        if isinstance(obj, _np.ndarray):
            return json_safe(obj.tolist())
    except ImportError:
        pass
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def should_big_mode(csv_path: Path) -> bool:
    try:
        size_mb = csv_path.stat().st_size / (1024 * 1024)
    except OSError:
        return False
    if size_mb >= env_int("OPS_BIGMODE_FILE_MB", 800):
        return True
    try:
        with open(csv_path, newline="", encoding="utf-8", errors="ignore") as f:
            header = next(csv.reader(f), [])
        if len(header) >= env_int("OPS_BIGMODE_COL_THRESHOLD", 2000):
            return True
    except Exception:
        pass
    return False


def load_csv(csv_path: Path, big_mode: bool):
    import pandas as pd

    if not big_mode:
        df = pd.read_csv(csv_path)
        return df, {"big_mode": False}
    sample_rows = env_int("OPS_BIGMODE_SAMPLE_ROWS", 1000)
    top_num = env_int("OPS_BIGMODE_TOP_NUMERIC", 300)
    top_cat = env_int("OPS_BIGMODE_TOP_CATEGORICAL", 40)
    with open(csv_path, newline="", encoding="utf-8", errors="ignore") as f:
        full_columns = next(csv.reader(f), [])
    sample = pd.read_csv(csv_path, nrows=sample_rows)
    num_cols = sample.select_dtypes(include="number").columns.tolist()[:top_num]
    cat_cols = [c for c in sample.columns if c not in num_cols][:top_cat]
    keep = list(dict.fromkeys(num_cols + cat_cols)) or list(sample.columns)
    df = pd.read_csv(csv_path, usecols=keep)
    return df, {
        "big_mode": True,
        "full_column_count": len(full_columns),
        "kept_columns": keep,
        "sample_rows": sample_rows,
    }


def normalize_columns(df):
    mapping = {c: snake_case(c) for c in df.columns}
    return df.rename(columns=mapping), mapping


def detect_timestamp(df):
    import pandas as pd

    for col in df.columns:
        lname = col.lower()
        if any(k in lname for k in ("time", "date", "timestamp", "datetime")):
            try:
                parsed = pd.to_datetime(df[col], errors="coerce")
                if parsed.notna().mean() > 0.8:
                    return col
            except Exception:
                continue
    for col in df.columns:
        if df[col].dtype == object:
            try:
                parsed = pd.to_datetime(df[col].head(50), errors="coerce")
                if parsed.notna().mean() > 0.8:
                    return col
            except Exception:
                continue
    return None


def profile_dataframe(df, meta_extra: dict | None = None) -> dict:
    import pandas as pd

    ts_col = detect_timestamp(df)
    numeric = df.select_dtypes(include="number")
    profile = {
        "shape": list(df.shape),
        "columns": [
            {
                "name": c,
                "dtype": str(df[c].dtype),
                "missing": int(df[c].isna().sum()),
                "missing_pct": round(float(df[c].isna().mean() * 100), 2),
                "n_unique": int(df[c].nunique(dropna=True)),
            }
            for c in df.columns
        ],
        "numeric_summary": json_safe(numeric.describe().to_dict())
        if not numeric.empty
        else {},
        "timestamp_column": ts_col,
        "timestamp_range": None,
        "candidate_id_columns": [
            c
            for c in df.columns
            if df[c].nunique(dropna=True) == len(df) and len(df) > 0
        ][:5],
        "is_time_series": bool(ts_col),
        "n_numeric": int(numeric.shape[1]),
        "n_categorical": int(df.shape[1] - numeric.shape[1]),
    }
    if ts_col:
        try:
            parsed = pd.to_datetime(df[ts_col], errors="coerce").dropna()
            if not parsed.empty:
                profile["timestamp_range"] = [str(parsed.min()), str(parsed.max())]
        except Exception:
            pass
    if meta_extra:
        profile["ingestion"] = meta_extra
    return json_safe(profile)


STAGE1_SYSTEM = (
    "You are a senior data-science planner. Given a dataset profile and a "
    "catalog of allowed methods, return ONLY a JSON analysis plan using keys: "
    "cleaning, missing_strategy, resampling, resample_rule, feature_engineering, "
    "analyses, supervised, supervised_target, visualizations, notes. "
    "Use only catalog values. Prefer simple robust methods. "
    "You do NOT compute metrics; the local Python engine executes the plan."
)


def build_stage1_prompt(profile: dict, target_hint: str | None = None) -> str:
    return (
        STAGE1_SYSTEM
        + "\n\nMETHOD_CATALOG:\n"
        + json.dumps(METHOD_CATALOG)
        + "\n\nDATASET_PROFILE:\n"
        + json.dumps(profile)[:6000]
        + ("\n\nSUGGESTED_TARGET: " + target_hint if target_hint else "")
        + "\n\nReturn ONLY the JSON plan object."
    )


def build_default_plan(profile: dict, target: str | None = None) -> dict:
    plan = json.loads(json.dumps(DEFAULT_PLAN))
    n_num = profile.get("n_numeric", 0)
    if profile.get("is_time_series"):
        plan["resampling"] = "time_grid_mean"
        plan["feature_engineering"] = ["time_features", "lags", "rolling_stats"]
        plan["analyses"] = ["correlation", "anomaly_detection", "forecasting"]
        plan["visualizations"] = ["histograms", "time_series", "forecast_plot"]
    elif n_num >= 2:
        plan["analyses"] = ["correlation", "clustering", "anomaly_detection"]
        plan["visualizations"] = [
            "histograms",
            "correlation_heatmap",
            "cluster_scatter",
        ]
    if target:
        plan["supervised"] = "random_forest_classifier"
        plan["supervised_target"] = target
    return plan


def validate_plan(raw: dict) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return json.loads(json.dumps(DEFAULT_PLAN)), [
            "Plan was not a JSON object; used default plan."
        ]
    plan = json.loads(json.dumps(DEFAULT_PLAN))
    cat = METHOD_CATALOG

    def check_list(key, allowed):
        vals = raw.get(key)
        if vals is None:
            return
        if not isinstance(vals, list):
            warnings.append(f"'{key}' was not a list; kept default.")
            return
        good = [v for v in vals if v in allowed]
        bad = [v for v in vals if v not in allowed]
        if bad:
            warnings.append(f"'{key}' dropped unsupported values: {bad}.")
        if good:
            plan[key] = good

    check_list("cleaning", cat["cleaning"])
    check_list("feature_engineering", cat["feature_engineering"])
    check_list("analyses", cat["analysis"])
    check_list("visualizations", cat["visualization"])

    ms = raw.get("missing_strategy")
    if isinstance(ms, str) and ms in ("median_mode", "ffill_bfill", "drop", "constant"):
        plan["missing_strategy"] = ms
    elif ms is not None:
        warnings.append(f"Unsupported missing_strategy '{ms}'; kept default.")
    rs = raw.get("resampling")
    if rs in cat["resampling"]:
        plan["resampling"] = rs
    elif rs is not None:
        warnings.append(f"Unsupported resampling '{rs}'; disabled.")
    rr = raw.get("resample_rule")
    if isinstance(rr, str) and re.fullmatch(
        r"\d+[hHDdTtMmSsWw]|15min|30min", (rr.strip() or "")
    ):
        plan["resample_rule"] = rr
    elif rr is not None:
        warnings.append("Unparseable resample_rule; kept '1h'.")
    sup = raw.get("supervised")
    if sup in cat["supervised"]:
        plan["supervised"] = sup
    elif sup is not None:
        warnings.append(f"Unsupported supervised '{sup}'; disabled.")
    tgt = raw.get("supervised_target")
    if tgt is None or (isinstance(tgt, str) and tgt):
        plan["supervised_target"] = tgt
    elif tgt is not None:
        warnings.append("Invalid supervised_target; ignored.")
    notes = raw.get("notes")
    if isinstance(notes, str) and notes.strip():
        plan["notes"] = notes.strip()[:1000]
    unknown = sorted(set(raw) - ALLOWED_TOP_KEYS)
    if unknown:
        warnings.append(f"Ignored unknown plan keys: {unknown}.")
    return plan, warnings


class PlanError(ValueError):
    pass


def extract_json_object(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise PlanError("No JSON object found in LLM response.")
    candidate = m.group(0)
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        candidate = re.sub(r"```(?:json)?", "", candidate).strip("` \n")
        obj = json.loads(candidate)
    if not isinstance(obj, dict):
        raise PlanError("LLM response JSON was not an object.")
    return obj


def gemini_api_generate(prompt: str, model: str, api_key: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={api_key}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        import requests

        resp = requests.post(url, json=payload, timeout=90)
        resp.raise_for_status()
        data = resp.json()
    except ImportError:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected Gemini API response shape: {e}")


def gemini_browser_generate(
    prompt: str, url_override: str | None, stage: str = "stage1"
) -> str:
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
    except ImportError as e:
        raise RuntimeError("Browser mode requires 'pip install selenium'.") from e
    default_url = "https://gemini.google.com/app"
    url = url_override or os.environ.get(
        "GEMINI_STAGE2_URL" if stage == "stage2" else "GEMINI_URL", default_url
    )
    options = webdriver.ChromeOptions()
    profile_dir = os.environ.get("GEMINI_BROWSER_PROFILE", "")
    if profile_dir:
        options.add_argument(f"--user-data-dir={profile_dir}")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        if os.environ.get("GEMINI_REQUIRE_LOGIN") == "1":
            input("Log in to Gemini in the opened browser, then press Enter here...")
        time.sleep(3)
        box = None
        for sel in ("div[contenteditable='true']", "textarea", "[role='textbox']"):
            try:
                box = driver.find_element(By.CSS_SELECTOR, sel)
                break
            except Exception:
                continue
        if box is None:
            raise RuntimeError(
                "Could not locate the Gemini prompt box (UI may have changed)."
            )
        box.click()
        box.send_keys(prompt[:12000])
        box.send_keys(Keys.CONTROL, Keys.ENTER)
        time.sleep(env_int("GEMINI_RETRY_DELAY_SECONDS", 20))
        return driver.find_element(By.TAG_NAME, "body").text
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def obtain_stage1_plan(profile, mode, model, key_file, target_hint):
    prompt = build_stage1_prompt(profile, target_hint)
    if mode == "off":
        plan = build_default_plan(profile, target_hint)
        validated, _ = validate_plan(plan)
        return validated, ["Offline mode: deterministic default plan."], "offline"
    try:
        if mode == "api":
            key = read_api_key(key_file)
            if not key:
                raise RuntimeError(
                    "No Gemini API key found (gemini_api_key.txt or env)."
                )
            text = gemini_api_generate(prompt, model, key)
            raw = extract_json_object(text)
            plan, warns = validate_plan(raw)
            return plan, warns, "gemini-api"
        if mode == "browser":
            text = gemini_browser_generate(prompt, None, stage="stage1")
            raw = extract_json_object(text)
            plan, warns = validate_plan(raw)
            warns.append("Browser mode is experimental; UI-dependent.")
            return plan, warns, "gemini-browser"
    except Exception as e:
        log.warning("Stage-1 LLM unavailable (%s); using default plan.", e)
        plan, warns = validate_plan(build_default_plan(profile, target_hint))
        warns.append(f"LLM fallback: {e}")
        return plan, warns, "fallback-offline"
    raise ValueError(f"Unknown gemini mode: {mode}")


def clean_dataframe(df, plan: dict):
    import pandas as pd

    steps = []
    if "drop_duplicates" in plan.get("cleaning", []):
        before = len(df)
        df = df.drop_duplicates()
        steps.append(f"dropped {before - len(df)} duplicate rows")
    strategy = plan.get("missing_strategy", "median_mode")
    if strategy == "drop":
        df = df.dropna()
        steps.append("dropped rows with missing values")
    elif strategy == "ffill_bfill":
        df = df.ffill().bfill()
        steps.append("forward/backward filled missing values")
    else:
        for c in df.columns:
            if df[c].isna().any():
                if df[c].dtype.kind in "biufc":
                    fill = df[c].median()
                else:
                    m = df[c].mode().dropna()
                    fill = m.iloc[0] if not m.empty else 0
                try:
                    df[c] = df[c].fillna(fill)
                except Exception:
                    pass
        steps.append("median/mode imputed missing values")
    if "iqr_clip" in plan.get("cleaning", []):
        num = df.select_dtypes(include="number").columns
        for c in num:
            q1, q3 = df[c].quantile(0.25), df[c].quantile(0.75)
            iqr = q3 - q1
            if pd.notna(iqr) and iqr > 0:
                df[c] = df[c].clip(q1 - 1.5 * iqr, q3 + 1.5 * iqr)
        steps.append("IQR-clipped numeric outliers")
    return df, steps


def engineer_features(df, plan: dict, ts_col: str | None):
    import pandas as pd

    feats = plan.get("feature_engineering", [])
    added: list[str] = []
    if ts_col and ts_col in df.columns and any(f != "disabled" for f in feats):
        ts = pd.to_datetime(df[ts_col], errors="coerce")
        if "time_features" in feats:
            df["hour"] = ts.dt.hour
            df["dayofweek"] = ts.dt.dayofweek
            df["month"] = ts.dt.month
            added += ["hour", "dayofweek", "month"]
        df = df.sort_values(ts_col).reset_index(drop=True)
        num = df.select_dtypes(include="number").columns.tolist()[:3]
        if "lags" in feats and num:
            for c in num:
                df[f"{c}_lag1"] = df[c].shift(1).bfill()
                added.append(f"{c}_lag1")
        if "rolling_stats" in feats and num:
            for c in num:
                df[f"{c}_rollmean3"] = df[c].rolling(3, min_periods=1).mean()
                added.append(f"{c}_rollmean3")
    return df, added


def run_correlation(df, out_tables: Path, max_cols: int) -> dict:
    num = df.select_dtypes(include="number")
    if num.shape[1] < 2:
        return {"status": "skipped", "reason": "fewer than 2 numeric columns"}
    cols = num.columns.tolist()[:max_cols]
    corr = num[cols].corr(numeric_only=True)
    corr.to_csv(out_tables / "correlation.csv")
    import numpy as np

    top = (
        corr.abs()
        .where(~np.eye(len(cols), dtype=bool))
        .stack()
        .sort_values(ascending=False)
        .head(10)
    )
    return {
        "status": "ok",
        "columns": cols,
        "top_pairs": [
            {"a": str(i[0]), "b": str(i[1]), "abs_corr": round(float(v), 3)}
            for i, v in top.items()
        ],
    }


def run_clustering(df, max_fit_rows: int) -> dict:
    num = df.select_dtypes(include="number").dropna()
    if num.shape[0] < 10 or num.shape[1] < 2:
        return {"status": "skipped", "reason": "not enough numeric data"}
    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return {"status": "skipped", "reason": "scikit-learn not installed"}
    fit = (
        num.sample(min(len(num), max_fit_rows), random_state=0)
        if len(num) > max_fit_rows
        else num
    )
    X = StandardScaler().fit_transform(fit.values)
    k = int(min(4, max(2, len(fit) // 20)))
    labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
    return {
        "status": "ok",
        "method": "KMeans",
        "k": k,
        "sizes": {str(i): int((labels == i).sum()) for i in range(k)},
        "fit_rows": len(fit),
    }


def run_anomaly(df) -> dict:
    num = df.select_dtypes(include="number").dropna()
    if num.shape[0] < 10:
        return {"status": "skipped", "reason": "not enough rows"}
    try:
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler

        X = StandardScaler().fit_transform(num.values)
        pred = IsolationForest(contamination=0.05, random_state=0).fit_predict(X)
        n = int((pred == -1).sum())
        return {
            "status": "ok",
            "method": "IsolationForest",
            "n_anomalies": n,
            "anomaly_pct": round(100 * n / len(pred), 2),
        }
    except ImportError:
        z = ((num - num.mean()) / num.std(ddof=0)).abs()
        n = int((z.max(axis=1) > 3).sum())
        return {
            "status": "ok",
            "method": "zscore-fallback",
            "n_anomalies": n,
            "anomaly_pct": round(100 * n / len(num), 2),
        }


def run_forecast(df, ts_col: str | None) -> dict:
    num = df.select_dtypes(include="number")
    if not ts_col or ts_col not in df.columns or num.empty:
        return {"status": "skipped", "reason": "no timestamp or numeric series"}
    try:
        import pandas as pd

        s = pd.to_datetime(df[ts_col], errors="coerce")
        target = num.columns[0]
        ordered = df.assign(_t=s).dropna(subset=["_t"]).sort_values("_t")
        y = ordered[target].astype(float).dropna()
        if len(y) < 12:
            return {"status": "skipped", "reason": "series too short"}
        split = int(len(y) * 0.8)
        train, test = y.iloc[:split], y.iloc[split:]
        pred = float(train.iloc[-1])
        mae = float((test - pred).abs().mean())
        rmse = float(((test - pred) ** 2).mean() ** 0.5)
        return {
            "status": "ok",
            "method": "naive-last-value-backtest",
            "target": str(target),
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "n_train": len(train),
            "n_test": len(test),
        }
    except Exception as e:
        return {"status": "skipped", "reason": str(e)}


def run_supervised(df, target: str | None, method: str, out_dir: Path) -> dict:
    if not target or method == "disabled":
        return {"status": "skipped", "reason": "supervised disabled"}
    if target not in df.columns:
        return {"status": "skipped", "reason": f"target '{target}' not found"}
    try:
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.linear_model import LinearRegression, LogisticRegression
        from sklearn.metrics import (
            accuracy_score,
            f1_score,
            mean_squared_error,
            r2_score,
        )
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder, StandardScaler
    except ImportError:
        return {"status": "skipped", "reason": "scikit-learn not installed"}
    X = df.drop(columns=[target])
    y = df[target]
    is_class = (y.dtype == object or y.nunique() <= 20) and method in (
        "logistic_regression",
        "random_forest_classifier",
    )
    num_c = X.select_dtypes(include="number").columns.tolist()
    cat_c = [c for c in X.columns if c not in num_c]
    pre = (
        ColumnTransformer(
            [
                ("num", StandardScaler(), num_c),
                ("cat", OneHotEncoder(handle_unknown="ignore"), cat_c),
            ]
        )
        if cat_c
        else StandardScaler()
    )
    if is_class:
        est = (
            LogisticRegression(max_iter=1000)
            if method == "logistic_regression"
            else RandomForestClassifier(n_estimators=100, random_state=0)
        )
    else:
        est = (
            LinearRegression()
            if method == "linear_regression"
            else RandomForestRegressor(n_estimators=100, random_state=0)
        )
    pipe = Pipeline([("pre", pre), ("model", est)])
    try:
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=0)
        pipe.fit(Xtr, ytr)
        pred = pipe.predict(Xte)
        if is_class:
            out = {
                "status": "ok",
                "task": "classification",
                "method": method,
                "accuracy": round(float(accuracy_score(yte, pred)), 4),
                "f1_macro": round(
                    float(f1_score(yte, pred, average="macro", zero_division=0)), 4
                ),
            }
        else:
            out = {
                "status": "ok",
                "task": "regression",
                "method": method,
                "rmse": round(float(mean_squared_error(yte, pred) ** 0.5), 4),
                "r2": round(float(r2_score(yte, pred)), 4),
            }
        try:
            import joblib

            (out_dir / "models").mkdir(parents=True, exist_ok=True)
            joblib.dump(pipe, out_dir / "models" / "supervised_pipeline.joblib")
            out["saved_pipeline"] = "models/supervised_pipeline.joblib"
        except Exception:
            pass
        return out
    except Exception as e:
        return {"status": "failed", "reason": str(e)[:300]}


def make_plots(
    df, results: dict, plan: dict, ts_col: str | None, figs: Path
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    saved: list[str] = []
    viz = set(plan.get("visualizations", []))

    def save(fig, name):
        p = figs / name
        fig.tight_layout()
        fig.savefig(p, dpi=110)
        plt.close(fig)
        saved.append(name)

    num = df.select_dtypes(include="number")
    if "histograms" in viz and not num.empty:
        n = min(3, num.shape[1])
        fig, axes = plt.subplots(1, n, figsize=(9, 3))
        if n == 1:
            axes = [axes]
        for ax, c in zip(axes, num.columns[:n]):
            ax.hist(num[c].dropna().values, bins=30)
            ax.set_title(c[:24])
        save(fig, "histograms.png")
    if (
        "correlation_heatmap" in viz
        and results.get("correlation", {}).get("status") == "ok"
    ):
        cols = results["correlation"]["columns"][:12]
        m = df[cols].corr(numeric_only=True).values
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.imshow(m, vmin=-1, vmax=1)
        ax.set_xticks(
            range(len(cols)),
            [c[:10] for c in cols],
            rotation=45,
            ha="right",
            fontsize=7,
        )
        ax.set_yticks(range(len(cols)), [c[:10] for c in cols], fontsize=7)
        ax.set_title("Correlation heatmap")
        save(fig, "correlation_heatmap.png")
    if "time_series" in viz and ts_col and ts_col in df.columns and not num.empty:
        try:
            import pandas as pd

            s = pd.to_datetime(df[ts_col], errors="coerce")
            fig, ax = plt.subplots(figsize=(9, 3))
            ax.plot(s.values[:500], num.iloc[:500, 0].values)
            ax.set_title(f"{num.columns[0][:24]} over time")
            save(fig, "time_series.png")
        except Exception:
            pass
    if "cluster_scatter" in viz and not num.empty and num.shape[1] >= 2:
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.scatter(
            num.iloc[:, 0].values[:1000], num.iloc[:, 1].values[:1000], s=8, alpha=0.6
        )
        ax.set_xlabel(num.columns[0][:20])
        ax.set_ylabel(num.columns[1][:20])
        ax.set_title("Scatter (first 2 numeric)")
        save(fig, "cluster_scatter.png")
    if "forecast_plot" in viz and results.get("forecast", {}).get("status") == "ok":
        fig, ax = plt.subplots(figsize=(9, 3))
        ax.text(
            0.5,
            0.5,
            f"Backtest RMSE={results['forecast']['rmse']} MAE={results['forecast']['mae']}",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_title("Forecast backtest summary")
        save(fig, "forecast_plot.png")
    return saved


def deterministic_sections(results: dict, profile: dict) -> dict:
    rows, cols = profile.get("shape", [0, 0])
    findings = []
    corr = results.get("correlation", {})
    if corr.get("status") == "ok" and corr.get("top_pairs"):
        top = corr["top_pairs"][0]
        findings.append(
            f"Strongest linear association is {top['a']} vs {top['b']} (|r|={top['abs_corr']})."
        )
    clu = results.get("clustering", {})
    if clu.get("status") == "ok":
        findings.append(
            f"Clustering (k={clu['k']}) separates {clu['fit_rows']} rows into groups of sizes {clu['sizes']}."
        )
    ano = results.get("anomaly", {})
    if ano.get("status") == "ok":
        findings.append(
            f"Anomaly screening flagged {ano['n_anomalies']} rows ({ano['anomaly_pct']}%) via {ano['method']}."
        )
    fc = results.get("forecast", {})
    if fc.get("status") == "ok":
        findings.append(
            f"Naive backtest on '{fc['target']}': RMSE={fc['rmse']}, MAE={fc['mae']}."
        )
    sup = results.get("supervised", {})
    if sup.get("status") == "ok":
        if sup.get("task") == "classification":
            findings.append(
                f"Supervised classification accuracy={sup['accuracy']}, F1-macro={sup['f1_macro']}."
            )
        else:
            findings.append(
                f"Supervised regression RMSE={sup['rmse']}, R2={sup['r2']}."
            )
    if not findings:
        findings.append(
            f"Dataset has {rows} rows and {cols} columns; no strong automated signals under the default plan."
        )
    recs = [
        "Validate top associations with domain context before acting.",
        "Review flagged anomalies for data-quality vs operational causes.",
    ]
    if sup.get("status") != "ok":
        recs.append("Re-run with --target <column> to enable supervised evaluation.")
    else:
        recs.append("Promote the saved pipeline only after holdout validation.")
    miss = [c for c in profile.get("columns", []) if c.get("missing_pct", 0) > 5][:3]
    lims = []
    if miss:
        lims.append(
            "Columns with notable missingness: "
            + ", ".join(c["name"] for c in miss)
            + "."
        )
    lims.append(
        "LLM narrative is evidence-grounded but not a substitute for domain review."
    )
    return {
        "key_findings": findings,
        "recommendations": recs,
        "limitations": lims,
        "executive_summary": f"Automated analysis of {rows} rows x {cols} columns produced {len(findings)} key finding(s). "
        + findings[0],
    }


def obtain_stage2_sections(results: dict, profile: dict, mode: str, model: str):
    if mode == "off":
        return deterministic_sections(results, profile), "offline-template"
    prompt = (
        "You are a data-science interpreter. Given COMPUTED results JSON "
        "(never invent numbers), write executive_summary, key_findings, "
        "recommendations, limitations as JSON. Results:\n"
        + json.dumps(json_safe(results))[:6000]
    )
    try:
        if mode == "api":
            key = read_api_key()
            if not key:
                raise RuntimeError("No API key for Stage-2.")
            text = gemini_api_generate(prompt, model, key)
        else:
            text = gemini_browser_generate(
                prompt, os.environ.get("GEMINI_STAGE2_URL"), stage="stage2"
            )
        raw = extract_json_object(text)
        for k in ("key_findings", "recommendations", "limitations"):
            if k in raw and not isinstance(raw[k], list):
                raw[k] = [str(raw[k])]
        if "key_findings" not in raw:
            raise PlanError("Stage-2 response missing key_findings.")
        return json_safe(raw), f"gemini-{mode}"
    except Exception as e:
        log.warning("Stage-2 LLM unavailable (%s); using deterministic template.", e)
        d = deterministic_sections(results, profile)
        d["_fallback"] = str(e)[:200]
        return d, "fallback-offline"


REPORT_PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=2.2cm]{geometry}
\usepackage{graphicx,booktabs,hyperref,xcolor,float}
\hypersetup{colorlinks=true,linkcolor=blue!60!black,urlcolor=blue!60!black}
\title{Autonomous Ops Analytics Report}
\author{LLM-Orchestrated Pipeline (Python execution engine)}
\date{DATEHERE}
\begin{document}
\maketitle
"""


def build_latex(
    run_id: str,
    profile: dict,
    plan: dict,
    results: dict,
    sections: dict,
    figures: list[str],
) -> str:
    L = [REPORT_PREAMBLE.replace("DATEHERE", datetime.date.today().isoformat())]
    L.append(f"Run ID: \\texttt{{{latex_escape(run_id)}}} \\\\\n")
    L.append(
        f"\\section{{Executive Summary}}\n{latex_escape(sections.get('executive_summary', ''))}\n"
    )
    L.append("\\section{Dataset Profile}\n")
    L.append(
        f"Rows: {profile.get('shape', [0, 0])[0]}, Columns: {profile.get('shape', [0, 0])[1]}. "
        f"Timestamp: {latex_escape(profile.get('timestamp_column') or 'none detected')}.\\\\\n"
    )
    L.append("\\begin{itemize}\n")
    for c in profile.get("columns", [])[:20]:
        L.append(
            f"\\item \\texttt{{{latex_escape(c['name'])}}} ({latex_escape(c['dtype'])}) "
            f"--- missing {c['missing_pct']}\\% \n"
        )
    L.append("\\end{itemize}\n")
    L.append("\\section{Analysis Plan (Stage-1)}\n\\begin{itemize}\n")
    for k in ("cleaning", "analyses", "feature_engineering", "visualizations"):
        L.append(
            f"\\item {latex_escape(k)}: {latex_escape(json.dumps(plan.get(k)))} \n"
        )
    L.append(
        f"\\item supervised: {latex_escape(json.dumps(plan.get('supervised')))} "
        f"target={latex_escape(plan.get('supervised_target') or 'n/a')} \n"
    )
    L.append("\\end{itemize}\n")
    L.append("\\section{Computed Results}\n")
    for name in ("correlation", "clustering", "anomaly", "forecast", "supervised"):
        r = results.get(name, {})
        L.append(f"\\subsection{{{latex_escape(name.title())}}}\n")
        L.append(
            "\\begin{verbatim}\n"
            + json.dumps(json_safe(r), indent=2)[:2000]
            + "\n\\end{verbatim}\n"
        )
    L.append("\\section{Key Findings (Stage-2)}\n\\begin{itemize}\n")
    for f in sections.get("key_findings", []):
        L.append(f"\\item {latex_escape(f)}\n")
    L.append("\\end{itemize}\n\\section{Recommendations}\n\\begin{itemize}\n")
    for f in sections.get("recommendations", []):
        L.append(f"\\item {latex_escape(f)}\n")
    L.append("\\end{itemize}\n\\section{Limitations}\n\\begin{itemize}\n")
    for f in sections.get("limitations", []):
        L.append(f"\\item {latex_escape(f)}\n")
    L.append("\\end{itemize}\n")
    if figures:
        L.append("\\section{Figures}\n")
        for fig in figures:
            L.append(
                f"\\begin{{figure}}[H]\\centering\n\\includegraphics[width=0.9\\textwidth]{{../figures/{latex_escape(fig)}}}\n"
                f"\\caption{{{latex_escape(fig)}}}\n\\end{{figure}}\n"
            )
    L.append(
        "\\section{Reproducibility}\nAll numbers in this report were computed locally by the "
        "deterministic Python engine; the LLM planned the methodology and interpreted the evidence. "
        "See \\texttt{profile.json}, \\texttt{gemini\\_plan.json}, \\texttt{manifest.json}. \n"
    )
    L.append("\\end{document}\n")
    return "".join(L)


def compile_pdf(tex_path: Path) -> bool:
    if shutil.which("pdflatex") is None:
        return False
    try:
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=tex_path.parent,
            capture_output=True,
            timeout=120,
        )
        return tex_path.with_suffix(".pdf").exists()
    except Exception:
        return False


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Autonomous Ops Analytics pipeline")
    p.add_argument("csv", help="Input CSV file")
    p.add_argument("--out", default="outputs", help="Output base directory")
    p.add_argument("--gemini-mode", choices=["off", "api", "browser"], default="off")
    p.add_argument("--gemini-model", default="gemini-2.5-flash")
    p.add_argument("--gemini-key-file", default=None)
    p.add_argument("--target", default=None, help="Supervised target column")
    p.add_argument("--run-id", default=None)
    p.add_argument("--no-plots", action="store_true")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    run_id = args.run_id or datetime.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"Input CSV not found: {csv_path}", file=sys.stderr)
        return 2
    out_base = Path(args.out)
    run_dir = out_base / run_id
    for sub in ("reports", "figures", "tables", "models"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(run_dir / "pipeline.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    log.info("Run %s starting (mode=%s).", run_id, args.gemini_mode)
    try:
        big = should_big_mode(csv_path)
        df, ing_meta = load_csv(csv_path, big)
        df, _colmap = normalize_columns(df)
        profile = profile_dataframe(df, ing_meta)
        (run_dir / "profile.json").write_text(
            json.dumps(profile, indent=2), encoding="utf-8"
        )
        target = snake_case(args.target) if args.target else None
        plan, plan_warns, plan_src = obtain_stage1_plan(
            profile, args.gemini_mode, args.gemini_model, args.gemini_key_file, target
        )
        if target and plan.get("supervised_target") in (None, "disabled"):
            plan["supervised_target"] = target
            if plan.get("supervised") == "disabled":
                plan["supervised"] = "random_forest_classifier"
        (run_dir / "gemini_plan.json").write_text(
            json.dumps(
                {"source": plan_src, "warnings": plan_warns, "plan": plan}, indent=2
            ),
            encoding="utf-8",
        )
        for w in plan_warns:
            log.warning("Plan: %s", w)
        df, clean_steps = clean_dataframe(df, plan)
        ts_col = profile.get("timestamp_column")
        df, added = engineer_features(df, plan, ts_col)
        log.info("Cleaning: %s; engineered: %s", clean_steps, added)
        results: dict = {}
        analyses = set(plan.get("analyses", []))
        if "correlation" in analyses:
            results["correlation"] = run_correlation(
                df, run_dir / "tables", env_int("OPS_MAX_CORR_COLS", 500)
            )
        if "clustering" in analyses:
            results["clustering"] = run_clustering(
                df, env_int("OPS_CLUSTER_MAX_FIT_ROWS", 5000)
            )
        if "anomaly_detection" in analyses:
            results["anomaly"] = run_anomaly(df)
        if "forecasting" in analyses:
            results["forecasting"] = run_forecast(df, ts_col)
            results["forecast"] = results["forecasting"]
        results["supervised"] = run_supervised(
            df,
            plan.get("supervised_target"),
            plan.get("supervised", "disabled"),
            run_dir,
        )
        results["_cleaning_steps"] = clean_steps
        results["_engineered_features"] = added
        figs: list[str] = []
        if not args.no_plots:
            try:
                figs = make_plots(df, results, plan, ts_col, run_dir / "figures")
            except Exception as e:
                log.warning("Plotting failed: %s", e)
        sections, stage2_src = obtain_stage2_sections(
            results, profile, args.gemini_mode, args.gemini_model
        )
        (run_dir / "gemini_stage2_sections.json").write_text(
            json.dumps({"source": stage2_src, "sections": sections}, indent=2),
            encoding="utf-8",
        )
        tex = build_latex(run_id, profile, plan, results, sections, figs)
        tex_path = run_dir / "reports" / f"{run_id}_report.tex"
        tex_path.write_text(tex, encoding="utf-8")
        pdf_ok = compile_pdf(tex_path)
        manifest = {
            "run_id": run_id,
            "created_utc": utc_now(),
            "version": VERSION,
            "mode": args.gemini_mode,
            "plan_source": plan_src,
            "stage2_source": stage2_src,
            "artifacts": {
                "profile": "profile.json",
                "plan": "gemini_plan.json",
                "stage2": "gemini_stage2_sections.json",
                "report_tex": f"reports/{tex_path.name}",
                "report_pdf": f"reports/{tex_path.stem}.pdf" if pdf_ok else None,
                "figures": [f"figures/{f}" for f in figs],
                "log": "pipeline.log",
            },
        }
        (run_dir / "manifest.json").write_text(
            json.dumps(json_safe(manifest), indent=2), encoding="utf-8"
        )
        log.info("Run %s complete. PDF=%s", run_id, pdf_ok)
        print(f"Done. Run directory: {run_dir}")
        return 0
    except Exception:
        log.exception("Pipeline failed.")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
