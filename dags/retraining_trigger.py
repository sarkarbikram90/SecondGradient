"""
DAG 3: Retraining Orchestration
================================
Triggered when:
  - drift_retrain_requested Airflow Variable is "true"
  - N consecutive drift runs have occurred
  - Current time is within business hours (configurable)

Tasks:
  1. check_retrain_conditions   – guards: variable flag + business hours
  2. prepare_training_dataset   – assemble training data from snapshots
  3. trigger_retraining         – kick off the actual retraining pipeline
  4. log_model_version          – record new model version / metadata
  5. reset_drift_counters       – clear consecutive counters
  6. notify_completion          – Slack success notification
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.utils.dates import days_ago

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = os.environ.get("SNAPSHOT_DIR", "/tmp/ml_drift/snapshots")
MODEL_REGISTRY_DIR = os.environ.get("MODEL_REGISTRY_DIR", "/tmp/ml_drift/model_registry")
SRC_DIR = str(Path(__file__).parents[1] / "src")


def _add_src():
    if SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)


# ---------------------------------------------------------------------------
# Task callables
# ---------------------------------------------------------------------------

def _check_retrain_conditions(**ctx) -> bool:
    """
    ShortCircuitOperator callable.
    Returns True (proceed) only when all conditions are met:
      1. drift_retrain_requested == "true"
      2. Current UTC hour is within business hours
    """
    _add_src()
    from drift.thresholds import load_thresholds

    # --- Guard 1: drift flag ---
    retrain_requested = Variable.get("drift_retrain_requested", default_var="false")
    if retrain_requested.lower() != "true":
        logger.info(
            "drift_retrain_requested=%s – no retrain needed. Skipping.", retrain_requested
        )
        return False

    # --- Guard 2: business hours ---
    thresholds = load_thresholds()
    allowed = thresholds.get("retrain_allowed_hours", {"start": 8, "end": 18})
    current_hour = datetime.now(timezone.utc).hour

    if not (allowed["start"] <= current_hour < allowed["end"]):
        logger.warning(
            "Current UTC hour=%d is outside business hours [%d, %d). Skipping retrain.",
            current_hour, allowed["start"], allowed["end"],
        )
        return False

    consecutive = int(Variable.get("drift_consecutive_count", default_var=0))
    required = thresholds.get("consecutive_runs_before_retrain", 3)
    if consecutive < required:
        logger.info(
            "Only %d consecutive drift runs (need %d). Skipping.", consecutive, required
        )
        return False

    logger.info(
        "All retrain conditions met (consecutive=%d, hour=%d UTC). Proceeding.",
        consecutive, current_hour,
    )
    return True


def _prepare_training_dataset(**ctx):
    """
    Assemble a fresh training dataset from recent inference snapshots.
    In production, replace this with your actual data pipeline logic.
    """
    import datetime as dt

    run_date = ctx["ds"]
    snapshot_dir = Path(SNAPSHOT_DIR)

    # Collect all available snapshots (up to 90 days)
    frames = []
    anchor = dt.date.fromisoformat(run_date)
    for i in range(90):
        date_str = str(anchor - dt.timedelta(days=i))
        for ext in ("parquet", "csv"):
            path = snapshot_dir / f"{date_str}.{ext}"
            if path.exists():
                df = pd.read_parquet(path) if ext == "parquet" else pd.read_csv(path)
                df["_snapshot_date"] = date_str
                frames.append(df)
                break

    if not frames:
        raise ValueError("No snapshot data found to build training dataset.")

    combined = pd.concat(frames, ignore_index=True)

    dataset_path = f"/tmp/ml_drift/retraining_dataset_{run_date}.parquet"
    combined.to_parquet(dataset_path, index=False)

    logger.info(
        "Training dataset prepared: %d rows from %d snapshots → %s",
        len(combined), len(frames), dataset_path,
    )
    ctx["ti"].xcom_push(key="dataset_path", value=dataset_path)


def _trigger_retraining(**ctx):
    """
    Trigger the retraining pipeline.

    Production options:
      - Trigger a Vertex AI / SageMaker training job via their SDK
      - Submit a Spark job via SparkSubmitOperator
      - Call an internal training service API
      - Run a subprocess / shell command

    Here we simulate a retraining run and write model metadata.
    """
    run_date = ctx["ds"]
    dataset_path = ctx["ti"].xcom_pull(key="dataset_path", task_ids="prepare_training_dataset")

    logger.info("🚀 Retraining pipeline triggered. Dataset: %s", dataset_path)

    # -----------------------------------------------------------------------
    # [REPLACE] with your actual retraining logic, e.g.:
    #   from your_ml_platform import submit_training_job
    #   job_id = submit_training_job(dataset_path=dataset_path, ...)
    # -----------------------------------------------------------------------

    # Simulate: create a stub model metadata file
    import hashlib, time
    run_id = hashlib.sha1(f"{run_date}{time.time()}".encode()).hexdigest()[:10]
    model_version = f"v_{run_date.replace('-', '')}_{run_id}"

    ctx["ti"].xcom_push(key="model_version", value=model_version)
    ctx["ti"].xcom_push(key="run_id", value=run_id)
    logger.info("Retraining job submitted. model_version=%s", model_version)


def _log_model_version(**ctx):
    """Record the new model version in the model registry directory."""
    ti = ctx["ti"]
    run_date = ctx["ds"]
    model_version = ti.xcom_pull(key="model_version", task_ids="trigger_retraining")
    run_id = ti.xcom_pull(key="run_id", task_ids="trigger_retraining")
    consecutive = int(Variable.get("drift_consecutive_count", default_var=0))

    registry_dir = Path(MODEL_REGISTRY_DIR)
    registry_dir.mkdir(parents=True, exist_ok=True)

    entry = {
        "model_version": model_version,
        "run_id": run_id,
        "retrain_date": run_date,
        "trigger_reason": "drift_threshold_breached",
        "consecutive_drift_runs": consecutive,
        "dag_id": ctx["dag"].dag_id,
        "logged_at": datetime.utcnow().isoformat(),
    }

    log_path = registry_dir / f"{model_version}.json"
    with open(log_path, "w") as f:
        json.dump(entry, f, indent=2)

    logger.info("Model version logged: %s → %s", model_version, log_path)
    ti.xcom_push(key="model_log_path", value=str(log_path))


def _reset_drift_counters(**ctx):
    """Reset the consecutive drift counter now that retraining is underway."""
    previous = Variable.get("drift_consecutive_count", default_var=0)
    Variable.set("drift_consecutive_count", 0)
    Variable.set("drift_retrain_requested", "false")
    logger.info(
        "Drift counters reset. Previous consecutive count: %s. "
        "drift_retrain_requested set to false.",
        previous,
    )


def _notify_completion(**ctx):
    """Send a Slack success notification after retraining has been triggered."""
    _add_src()
    from alerts.slack import send_slack_alert

    ti = ctx["ti"]
    model_version = ti.xcom_pull(key="model_version", task_ids="trigger_retraining")
    run_date = ctx["ds"]

    message = (
        f"✅ *ML Retraining Triggered* — `{ctx['dag'].dag_id}` | `{run_date}`\n"
        f"New model version: *{model_version}*\n"
        "Drift counters reset. Monitoring continues."
    )

    send_slack_alert(
        message,
        severity="ok",
        fields=[
            {"title": "Model Version", "value": model_version},
            {"title": "Trigger Date", "value": run_date},
        ],
    )


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
default_args = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=15),
    "email_on_failure": False,
}

with DAG(
    dag_id="retraining_trigger",
    default_args=default_args,
    description="Orchestrate model retraining when drift persists beyond threshold",
    schedule_interval="0 8 * * *",  # 08:00 UTC daily – polled check
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "drift", "retraining"],
) as dag:

    check_conditions = ShortCircuitOperator(
        task_id="check_retrain_conditions",
        python_callable=_check_retrain_conditions,
        ignore_downstream_trigger_rules=True,
    )

    prepare_dataset = PythonOperator(
        task_id="prepare_training_dataset",
        python_callable=_prepare_training_dataset,
    )

    trigger_retrain = PythonOperator(
        task_id="trigger_retraining",
        python_callable=_trigger_retraining,
    )

    log_version = PythonOperator(
        task_id="log_model_version",
        python_callable=_log_model_version,
    )

    reset_counters = PythonOperator(
        task_id="reset_drift_counters",
        python_callable=_reset_drift_counters,
    )

    notify = PythonOperator(
        task_id="notify_completion",
        python_callable=_notify_completion,
    )

    done = EmptyOperator(task_id="retraining_complete")

    # Wiring
    check_conditions >> prepare_dataset >> trigger_retrain >> log_version >> reset_counters >> notify >> done