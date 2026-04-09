"""
DAG 1: Inference Data Ingestion
================================
Reads raw prediction logs, validates schema, and stores date-partitioned snapshots.

Schedule:  Daily at 01:00 UTC (configurable).
Catchup:   Enabled – safely backfills missing partitions.

Tasks:
  1. check_source_availability  – sensor / readiness check
  2. load_raw_inference_data    – read CSV / Parquet / DB
  3. validate_schema            – enforce expected schema
  4. save_snapshot              – write partitioned snapshot
  5. notify_success / notify_failure – optional Slack notification
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.dates import days_ago

# ---------------------------------------------------------------------------
# Paths / env
# ---------------------------------------------------------------------------
RAW_INFERENCE_DIR = os.environ.get("RAW_INFERENCE_DIR", "/opt/airflow/data/raw_inference")
SNAPSHOT_DIR = os.environ.get("SNAPSHOT_DIR", "/opt/airflow/data/snapshots")

ARTIFACT_DIR = Path(os.environ.get('ARTIFACT_DIR', '/opt/airflow/data/artifacts'))
try:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        ARTIFACT_DIR.chmod(0o700)
    except Exception:
        pass
except Exception:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default args
# ---------------------------------------------------------------------------
default_args = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

# ---------------------------------------------------------------------------
# Task callables
# ---------------------------------------------------------------------------

def _check_source_availability(**ctx) -> str:
    """
    Check that a raw inference file exists for the logical date.
    Branches to 'handle_late_data' if missing, else 'load_raw_inference_data'.
    """
    run_date = ctx["ds"]  # e.g. "2024-07-15"
    raw_dir = Path(RAW_INFERENCE_DIR)

    for ext in ("parquet", "csv", "json"):
        candidate = raw_dir / f"{run_date}.{ext}"
        if candidate.exists():
            logger.info("Source file found: %s", candidate)
            return "load_raw_inference_data"

    logger.warning("No source file for %s – routing to handle_late_data", run_date)
    return "handle_late_data"


def _load_raw_inference_data(**ctx):
    """Read raw inference logs for the logical date and push to XCom."""
    run_date = ctx["ds"]
    raw_dir = Path(RAW_INFERENCE_DIR)

    for ext in ("parquet", "csv", "json"):
        path = raw_dir / f"{run_date}.{ext}"
        if path.exists():
            if ext == "parquet":
                df = pd.read_parquet(path)
            elif ext == "csv":
                df = pd.read_csv(path)
            else:
                df = pd.read_json(path)
            logger.info("Loaded %d rows from %s", len(df), path)
            # Push serialisable summary; full data is saved to disk in next step
            ctx["ti"].xcom_push(key="row_count", value=len(df))
            ctx["ti"].xcom_push(key="columns", value=df.columns.tolist())
            # Persist df to a temp parquet so the next task can read it
            ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
            tmp = ARTIFACT_DIR / f"raw_{run_date}_{uuid4().hex}.parquet"
            df.to_parquet(tmp, index=False)
            try:
                os.chmod(tmp, 0o600)
            except Exception:
                pass
            ctx["ti"].xcom_push(key="tmp_artifact_uri", value=str(tmp))
            return
    raise FileNotFoundError(f"Raw inference file not found for {run_date}")


def _validate_schema(**ctx):
    """Validate the loaded DataFrame against the expected schema."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
    from data.validators import SchemaSpec, assert_valid

    run_date = ctx["ds"]
    tmp_artifact_uri = ctx["ti"].xcom_pull(key="tmp_artifact_uri", task_ids="load_raw_inference_data")

    df = pd.read_parquet(tmp_artifact_uri)

    # Configure expected schema – adjust required_columns to your model's feature set
    spec = SchemaSpec(
        required_columns=["timestamp", "prediction_score"],
        numeric_columns=["prediction_score"],
        nullable_columns=["feature_3"],
        max_null_rate=0.05,
        min_rows=10,
    )

    assert_valid(df, spec)
    logger.info("Schema validation passed for %s (%d rows)", run_date, len(df))


def _save_snapshot(**ctx):
    """Persist the validated inference data as a date-partitioned snapshot."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
    from data.loaders import save_snapshot

    run_date = ctx["ds"]
    tmp_artifact_uri = ctx["ti"].xcom_pull(key="tmp_artifact_uri", task_ids="load_raw_inference_data")
    df = pd.read_parquet(tmp_artifact_uri)

    saved_path = save_snapshot(df, run_date, snapshot_dir=SNAPSHOT_DIR, fmt="parquet")
    logger.info("Snapshot saved: %s", saved_path)
    ctx["ti"].xcom_push(key="snapshot_path", value=str(saved_path))

    # Clean up temp file
    Path(tmp_artifact_uri).unlink(missing_ok=True)


def _handle_late_data(**ctx):
    """
    Handles the case where inference data arrives late.
    Could implement a wait-and-retry strategy or mark as skipped.
    """
    run_date = ctx["ds"]
    logger.warning(
        "Late data handler triggered for %s. "
        "Consider checking the upstream pipeline or extending the sensor timeout.",
        run_date,
    )
    # In production: raise AirflowSkipException() or trigger a PagerDuty alert


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="inference_data_ingestion",
    default_args=default_args,
    description="Ingest and validate daily ML inference logs into snapshots",
    schedule_interval="0 1 * * *",  # 01:00 UTC daily
    start_date=days_ago(7),
    catchup=True,
    max_active_runs=3,
    tags=["ml", "drift", "ingestion"],
) as dag:

    check_source = BranchPythonOperator(
        task_id="check_source_availability",
        python_callable=_check_source_availability,
    )

    handle_late = PythonOperator(
        task_id="handle_late_data",
        python_callable=_handle_late_data,
    )

    load_raw = PythonOperator(
        task_id="load_raw_inference_data",
        python_callable=_load_raw_inference_data,
    )

    validate = PythonOperator(
        task_id="validate_schema",
        python_callable=_validate_schema,
    )

    save = PythonOperator(
        task_id="save_snapshot",
        python_callable=_save_snapshot,
    )

    done = EmptyOperator(
        task_id="ingestion_complete",
        trigger_rule="none_failed_min_one_success",
    )

    # DAG wiring
    check_source >> [load_raw, handle_late]
    load_raw >> validate >> save >> done
    handle_late >> done