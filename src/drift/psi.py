"""
Population Stability Index (PSI) computation for detecting distribution drift.
PSI < 0.1  → No significant change
PSI 0.1-0.2 → Moderate change (warning)
PSI > 0.2  → Significant change (alert)
"""
import numpy as np
import pandas as pd
from typing import Union


def compute_psi(
    baseline: Union[np.ndarray, pd.Series],
    current: Union[np.ndarray, pd.Series],
    buckets: int = 10,
    epsilon: float = 1e-4,
) -> float:
    """
    Compute PSI between a baseline distribution and a current distribution.

    Args:
        baseline: Reference distribution (training data).
        current:  Recent inference data distribution.
        buckets:  Number of bins for discretisation.
        epsilon:  Small constant to avoid log(0).

    Returns:
        PSI score (float).
    """
    baseline = np.asarray(baseline, dtype=float)
    current = np.asarray(current, dtype=float)

    # Build bins from the baseline
    breakpoints = np.percentile(baseline, np.linspace(0, 100, buckets + 1))
    breakpoints = np.unique(breakpoints)  # remove duplicate edges

    baseline_counts = np.histogram(baseline, bins=breakpoints)[0]
    current_counts = np.histogram(current, bins=breakpoints)[0]

    baseline_pct = baseline_counts / len(baseline) + epsilon
    current_pct = current_counts / len(current) + epsilon

    psi_value = np.sum((current_pct - baseline_pct) * np.log(current_pct / baseline_pct))
    return float(psi_value)


def compute_psi_dataframe(
    baseline_df: pd.DataFrame,
    current_df: pd.DataFrame,
    feature_columns: list,
    buckets: int = 10,
) -> pd.DataFrame:
    """
    Compute per-feature PSI for all specified columns.

    Returns:
        DataFrame with columns [feature, psi, severity].
    """
    records = []
    for col in feature_columns:
        if col not in baseline_df.columns or col not in current_df.columns:
            continue
        psi = compute_psi(baseline_df[col].dropna(), current_df[col].dropna(), buckets)
        severity = _psi_severity(psi)
        records.append({"feature": col, "psi": round(psi, 6), "severity": severity})
    return pd.DataFrame(records)


def _psi_severity(psi: float) -> str:
    if psi < 0.1:
        return "ok"
    elif psi < 0.2:
        return "warning"
    return "critical"