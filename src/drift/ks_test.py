"""
Kolmogorov-Smirnov (KS) test for detecting distribution drift.

The KS statistic measures the maximum distance between two CDFs.
A low p-value (< threshold) indicates the distributions are significantly different.
"""
import numpy as np
import pandas as pd
from scipy import stats
from typing import Union


def compute_ks(
    baseline: Union[np.ndarray, pd.Series],
    current: Union[np.ndarray, pd.Series],
) -> dict:
    """
    Run a two-sample KS test between baseline and current distributions.

    Returns:
        dict with keys: statistic, p_value, drifted (bool).
    """
    baseline = np.asarray(baseline, dtype=float)
    current = np.asarray(current, dtype=float)

    result = stats.ks_2samp(baseline, current)
    return {
        "statistic": round(float(result.statistic), 6),
        "p_value": round(float(result.pvalue), 6),
    }


def compute_ks_dataframe(
    baseline_df: pd.DataFrame,
    current_df: pd.DataFrame,
    feature_columns: list,
    p_value_threshold: float = 0.05,
) -> pd.DataFrame:
    """
    Run KS test per feature and return a summary DataFrame.

    Returns:
        DataFrame with columns [feature, ks_statistic, p_value, drifted].
    """
    records = []
    for col in feature_columns:
        if col not in baseline_df.columns or col not in current_df.columns:
            continue
        result = compute_ks(baseline_df[col].dropna(), current_df[col].dropna())
        result["feature"] = col
        result["drifted"] = result["p_value"] < p_value_threshold
        result["ks_statistic"] = result.pop("statistic")
        records.append(result)
    return pd.DataFrame(records)[["feature", "ks_statistic", "p_value", "drifted"]]


def compute_mean_variance_shift(
    baseline_df: pd.DataFrame,
    current_df: pd.DataFrame,
    feature_columns: list,
) -> pd.DataFrame:
    """
    Compute mean and variance shift per feature.

    Returns:
        DataFrame with columns [feature, baseline_mean, current_mean,
                                  mean_shift_pct, baseline_var, current_var, var_shift_pct].
    """
    records = []
    for col in feature_columns:
        if col not in baseline_df.columns or col not in current_df.columns:
            continue
        b = baseline_df[col].dropna()
        c = current_df[col].dropna()

        b_mean, c_mean = float(b.mean()), float(c.mean())
        b_var, c_var = float(b.var()), float(c.var())

        mean_shift_pct = abs(c_mean - b_mean) / (abs(b_mean) + 1e-9) * 100
        var_shift_pct = abs(c_var - b_var) / (abs(b_var) + 1e-9) * 100

        records.append(
            {
                "feature": col,
                "baseline_mean": round(b_mean, 6),
                "current_mean": round(c_mean, 6),
                "mean_shift_pct": round(mean_shift_pct, 2),
                "baseline_var": round(b_var, 6),
                "current_var": round(c_var, 6),
                "var_shift_pct": round(var_shift_pct, 2),
            }
        )
    return pd.DataFrame(records)