"""
Threshold configuration and decision engine for drift evaluation.
Loads thresholds from YAML config and evaluates drift results.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


DEFAULT_THRESHOLDS = {
    "psi": {"warning": 0.1, "critical": 0.2},
    "ks_p_value": 0.05,
    "mean_shift_pct": 10.0,
    "var_shift_pct": 20.0,
    "consecutive_runs_before_retrain": 3,
}


def load_thresholds(config_path: str | None = None) -> dict:
    """
    Load drift thresholds from YAML config file.
    Falls back to DEFAULT_THRESHOLDS if the file is not found.
    """
    if config_path is None:
        config_path = os.environ.get(
            "DRIFT_CONFIG_PATH",
            str(Path(__file__).parents[2] / "configs" / "drift_thresholds.yaml"),
        )

    try:
        with open(config_path, "r") as f:
            user_config = yaml.safe_load(f)
        # Merge with defaults so missing keys are always present
        merged = {**DEFAULT_THRESHOLDS, **(user_config or {})}
        return merged
    except FileNotFoundError:
        return DEFAULT_THRESHOLDS


class DriftDecisionEngine:
    """
    Evaluates computed drift metrics against configured thresholds
    and decides whether to alert or trigger retraining.
    """

    def __init__(self, thresholds: dict | None = None):
        self.thresholds = thresholds or load_thresholds()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        psi_df: pd.DataFrame,
        ks_df: pd.DataFrame,
        shift_df: pd.DataFrame,
    ) -> dict[str, Any]:
        """
        Evaluate all drift metrics and return a structured verdict.

        Returns:
            {
                "overall_status": "ok" | "warning" | "critical",
                "should_alert": bool,
                "should_retrain": bool,
                "feature_verdicts": {feature: status, ...},
                "summary": str,
            }
        """
        feature_verdicts: dict[str, str] = {}

        # PSI evaluation
        if not psi_df.empty:
            for _, row in psi_df.iterrows():
                feature_verdicts[row["feature"]] = row["severity"]

        # KS evaluation
        if not ks_df.empty and "drifted" in ks_df.columns:
            for _, row in ks_df.iterrows():
                if row["drifted"]:
                    existing = feature_verdicts.get(row["feature"], "ok")
                    feature_verdicts[row["feature"]] = _escalate(existing, "warning")

        # Mean / variance shift
        mean_thr = self.thresholds.get("mean_shift_pct", DEFAULT_THRESHOLDS["mean_shift_pct"])
        var_thr = self.thresholds.get("var_shift_pct", DEFAULT_THRESHOLDS["var_shift_pct"])
        if not shift_df.empty:
            for _, row in shift_df.iterrows():
                feat = row["feature"]
                status = "ok"
                if row["mean_shift_pct"] > mean_thr or row["var_shift_pct"] > var_thr:
                    status = "warning"
                existing = feature_verdicts.get(feat, "ok")
                feature_verdicts[feat] = _escalate(existing, status)

        # Aggregate
        statuses = list(feature_verdicts.values()) or ["ok"]
        if "critical" in statuses:
            overall = "critical"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "ok"

        should_alert = overall in ("warning", "critical")
        should_retrain = overall == "critical"

        n_drifted = sum(1 for s in statuses if s != "ok")
        summary = (
            f"Drift evaluation complete. "
            f"Status={overall}. "
            f"{n_drifted}/{len(statuses)} features drifted."
        )

        return {
            "overall_status": overall,
            "should_alert": should_alert,
            "should_retrain": should_retrain,
            "feature_verdicts": feature_verdicts,
            "summary": summary,
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_SEVERITY_ORDER = {"ok": 0, "warning": 1, "critical": 2}


def _escalate(current: str, new: str) -> str:
    """Return the higher-severity status."""
    return current if _SEVERITY_ORDER.get(current, 0) >= _SEVERITY_ORDER.get(new, 0) else new