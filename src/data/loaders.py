"""
Data loaders for baseline (training) statistics and recent inference snapshots.
Supports CSV, Parquet, and JSON sources.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (overridable via environment variables)
# ---------------------------------------------------------------------------
SNAPSHOT_DIR = Path(os.environ.get("SNAPSHOT_DIR", "/tmp/ml_drift/snapshots"))
BASELINE_PATH = Path(
    os.environ.get("BASELINE_PATH", "/tmp/ml_drift/baseline/baseline_stats.parquet")
)


def load_baseline(path: str | Path | None = None) -> pd.DataFrame:
    """
    Load baseline (training-time) statistics from a file.

    Supports .parquet, .csv, and .json.
    The DataFrame should contain one row per feature with statistical summary columns
    (mean, std, min, max, percentiles, etc.) OR raw training samples.

    Args:
        path: Override path. Falls back to BASELINE_PATH env var or default.

    Returns:
        pd.DataFrame with baseline feature data.
    """
    path = Path(path or BASELINE_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"Baseline file not found at '{path}'. "
            "Set the BASELINE_PATH environment variable or pass an explicit path."
        )
    return _read_dataframe(path)


def load_inference_snapshot(
    run_date: str,
    snapshot_dir: str | Path | None = None,
) -> pd.DataFrame:
    """
    Load a date-partitioned inference snapshot.

    Looks for files named:
        <snapshot_dir>/<run_date>.parquet  (preferred)
        <snapshot_dir>/<run_date>.csv

    Args:
        run_date: Airflow logical date string, e.g. "2024-07-15".
        snapshot_dir: Directory containing snapshots.

    Returns:
        pd.DataFrame with inference log data for that partition.
    """
    base_dir = Path(snapshot_dir or SNAPSHOT_DIR)
    for ext in ("parquet", "csv", "json"):
        candidate = base_dir / f"{run_date}.{ext}"
        if candidate.exists():
            logger.info("Loading inference snapshot: %s", candidate)
            return _read_dataframe(candidate)
    raise FileNotFoundError(
        f"No inference snapshot found for date '{run_date}' in '{base_dir}'. "
        "Expected a file named <date>.parquet / .csv / .json"
    )


def load_recent_inference(
    n_days: int = 7,
    snapshot_dir: str | Path | None = None,
    run_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load and concatenate inference snapshots for the last N days.

    Args:
        n_days:       Number of most-recent snapshots to include.
        snapshot_dir: Directory to search.
        run_date:     If given, treat as the most recent date.

    Returns:
        Combined pd.DataFrame.
    """
    import datetime

    base_dir = Path(snapshot_dir or SNAPSHOT_DIR)
    if not base_dir.exists():
        raise FileNotFoundError(f"Snapshot directory '{base_dir}' does not exist.")

    if run_date:
        anchor = datetime.date.fromisoformat(run_date)
    else:
        anchor = datetime.date.today()

    frames = []
    for i in range(n_days):
        date_str = str(anchor - datetime.timedelta(days=i))
        try:
            df = load_inference_snapshot(date_str, snapshot_dir=base_dir)
            df["_snapshot_date"] = date_str
            frames.append(df)
        except FileNotFoundError:
            logger.warning("Snapshot missing for %s – skipping.", date_str)

    if not frames:
        raise ValueError(
            f"No snapshots found in the last {n_days} days ending at '{anchor}'."
        )

    return pd.concat(frames, ignore_index=True)


def save_snapshot(
    df: pd.DataFrame,
    run_date: str,
    snapshot_dir: str | Path | None = None,
    fmt: str = "parquet",
) -> Path:
    """
    Persist an inference DataFrame as a date-partitioned snapshot.

    Args:
        df:           DataFrame to save.
        run_date:     Partition date string.
        snapshot_dir: Directory to write into (created if missing).
        fmt:          "parquet" or "csv".

    Returns:
        Path to the written file.
    """
    base_dir = Path(snapshot_dir or SNAPSHOT_DIR)
    base_dir.mkdir(parents=True, exist_ok=True)
    dest = base_dir / f"{run_date}.{fmt}"

    if fmt == "parquet":
        df.to_parquet(dest, index=False)
    elif fmt == "csv":
        df.to_csv(dest, index=False)
    else:
        raise ValueError(f"Unsupported format '{fmt}'. Choose 'parquet' or 'csv'.")

    logger.info("Snapshot saved: %s (%d rows)", dest, len(df))
    return dest


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_dataframe(path: Path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext == ".parquet":
        return pd.read_parquet(path)
    elif ext == ".csv":
        return pd.read_csv(path)
    elif ext == ".json":
        return pd.read_json(path)
    else:
        raise ValueError(f"Unsupported file extension '{ext}' for path '{path}'.")