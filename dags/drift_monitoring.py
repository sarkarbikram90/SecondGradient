"""
DAG 2: Drift Detection (Hero DAG)
===================================
Loads baseline and recent inference snapshots, computes multiple drift metrics,
persists results, and branches to alert or trigger retraining.

Schedule:  Daily at 06:00 UTC (after ingestion completes).
Depends:   inference_data_ingestion DAG should complete first.

Tasks:
  1. load_baseline              – load training distribution stats
  2. load_recent_inference      – load last N days of snapshots
  3. compute_drift_metrics      – PSI + KS + mean/variance shift
  4. persist_drift_results      – save metrics to disk / DB
  5. evaluate_thresholds        – decide: ok / warning / critical
  6. branch_on_verdict          – route to alert or skip
  7. send_drift_alert           – Slack notification
  8. flag_for_retraining        – set Airflow Variable for DAG 3
  9. drift_check_complete       – join point
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd
from airflow import DAG
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.utils.dates import days_ago

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = os.environ.get("SNAPSHOT_DIR", "/opt/airflow/data/snapshots")
BASELINE_PATH = os.environ.get("BASELINE_PATH", "/opt/airflow/data/baseline/baseline_stats.parquet")
DRIFT_RESULTS_DIR = os.environ.get("DRIFT_RESULTS_DIR", "/opt/airflow/data/drift_results")
RECENT_DAYS = int(os.environ.get("RECENT_INFERENCE_DAYS", "7"))

ARTIFACT_DIR = Path(os.environ.get('ARTIFACT_DIR', '/opt/airflow/data/artifacts'))
try:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        ARTIFACT_DIR.chmod(0o700)
    except Exception:
        pass
except Exception:
    pass

SRC_DIR = str(Path(__file__).parents[1] / "src")


def _add_src():
    if SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)


# ---------------------------------------------------------------------------
# Task callables
# ---------------------------------------------------------------------------

def _load_baseline(**ctx):
    _add_src()
    from data.loaders import load_baseline
    df = load_baseline(path=BASELINE_PATH)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ARTIFACT_DIR / f"baseline_{uuid4().hex}.parquet"
    df.to_parquet(tmp, index=False)
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    ctx["ti"].xcom_push(key="baseline_artifact_uri", value=str(tmp))
    logger.info("Baseline loaded: %d rows, columns=%s", len(df), df.columns.tolist())


def _load_recent_inference(**ctx):
    _add_src()
    from data.loaders import load_recent_inference

    run_date = ctx["ds"]
    df = load_recent_inference(n_days=RECENT_DAYS, snapshot_dir=SNAPSHOT_DIR, run_date=run_date)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ARTIFACT_DIR / f"recent_{run_date}_{uuid4().hex}.parquet"
    df.to_parquet(tmp, index=False)
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    ctx["ti"].xcom_push(key="recent_artifact_uri", value=str(tmp))
    logger.info("Recent inference loaded: %d rows", len(df))


def _compute_drift_metrics(**ctx):
    _add_src()
    from drift.psi import compute_psi_dataframe
    from drift.ks_test import compute_ks_dataframe, compute_mean_variance_shift

    ti = ctx["ti"]
    baseline_tmp = ti.xcom_pull(key="baseline_artifact_uri", task_ids="load_baseline")
    recent_tmp = ti.xcom_pull(key="recent_artifact_uri", task_ids="load_recent_inference")

    baseline_df = pd.read_parquet(baseline_tmp)
    current_df = pd.read_parquet(recent_tmp)

    # Identify numeric feature columns (exclude internal metadata columns)
    numeric_cols = [
        c for c in baseline_df.select_dtypes(include="number").columns
        if c in current_df.columns and not c.startswith("_")
    ]
    logger.info("Computing drift for features: %s", numeric_cols)

    psi_df = compute_psi_dataframe(baseline_df, current_df, numeric_cols)
    ks_df_raw = compute_ks_dataframe(baseline_df, current_df, numeric_cols)
    # Rename for clarity
    ks_df = ks_df_raw.rename(columns={"statistic": "ks_statistic"}) if "statistic" in ks_df_raw.columns else ks_df_raw
    shift_df = compute_mean_variance_shift(baseline_df, current_df, numeric_cols)

    run_date = ctx["ds"]
    results_dir = Path(DRIFT_RESULTS_DIR) / run_date
    results_dir.mkdir(parents=True, exist_ok=True)

    psi_path = str(results_dir / "psi.parquet")
    ks_path = str(results_dir / "ks.parquet")
    shift_path = str(results_dir / "shift.parquet")

    psi_df.to_parquet(psi_path, index=False)
    try:
        os.chmod(psi_path, 0o600)
    except Exception:
        pass
    ks_df.to_parquet(ks_path, index=False)
    try:
        os.chmod(ks_path, 0o600)
    except Exception:
        pass
    shift_df.to_parquet(shift_path, index=False)
    try:
        os.chmod(shift_path, 0o600)
    except Exception:
        pass

    ti.xcom_push(key="psi_path", value=psi_path)
    ti.xcom_push(key="ks_path", value=ks_path)
    ti.xcom_push(key="shift_path", value=shift_path)

    logger.info("Drift metrics computed. PSI summary rows=%d", len(psi_df))


def _persist_drift_results(**ctx):
    """Save a consolidated JSON drift report for audit/dashboard consumption."""
    ti = ctx["ti"]
    run_date = ctx["ds"]

    psi_df = pd.read_parquet(ti.xcom_pull(key="psi_path", task_ids="compute_drift_metrics"))
    ks_df = pd.read_parquet(ti.xcom_pull(key="ks_path", task_ids="compute_drift_metrics"))
    shift_df = pd.read_parquet(ti.xcom_pull(key="shift_path", task_ids="compute_drift_metrics"))

    report = {
        "run_date": run_date,
        "dag_id": ctx["dag"].dag_id,
        "psi": psi_df.to_dict(orient="records"),
        "ks": ks_df.to_dict(orient="records"),
        "shift": shift_df.to_dict(orient="records"),
    }

    report_path = Path(DRIFT_RESULTS_DIR) / run_date / "drift_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    try:
        os.chmod(report_path, 0o600)
    except Exception:
        pass

    logger.info("Drift report persisted: %s", report_path)
    ti.xcom_push(key="report_path", value=str(report_path))


def _evaluate_thresholds(**ctx) -> str:
    """
    Evaluate drift metrics against thresholds.
    Returns the task_id for the branch to follow.
    """
    _add_src()
    from drift.thresholds import DriftDecisionEngine

    ti = ctx["ti"]
    psi_df = pd.read_parquet(ti.xcom_pull(key="psi_path", task_ids="compute_drift_metrics"))
    ks_df = pd.read_parquet(ti.xcom_pull(key="ks_path", task_ids="compute_drift_metrics"))
    shift_df = pd.read_parquet(ti.xcom_pull(key="shift_path", task_ids="compute_drift_metrics"))

    engine = DriftDecisionEngine()
    verdict = engine.evaluate(psi_df, ks_df, shift_df)

    logger.info("Drift verdict: %s", verdict["summary"])
    ti.xcom_push(key="verdict", value=json.dumps(verdict))

    if verdict["should_retrain"]:
        return "flag_for_retraining"
    elif verdict["should_alert"]:
        return "send_drift_alert"
    return "drift_check_complete"


def _send_drift_alert(**ctx):
    _add_src()
    from alerts.slack import send_drift_alert

    ti = ctx["ti"]
    verdict_raw = ti.xcom_pull(key="verdict", task_ids="evaluate_thresholds")
    verdict = json.loads(verdict_raw)
    run_date = ctx["ds"]
    dag_id = ctx["dag"].dag_id

    send_drift_alert(verdict, run_date, dag_id)


def _flag_for_retraining(**ctx):
    """
    Increment the consecutive drift counter in Airflow Variables.
    When it reaches the configured threshold, the retraining DAG will pick it up.
    """
    _add_src()
    from drift.thresholds import load_thresholds
    from alerts.slack import send_drift_alert

    ti = ctx["ti"]
    verdict_raw = ti.xcom_pull(key="verdict", task_ids="evaluate_thresholds")
    verdict = json.loads(verdict_raw)
    run_date = ctx["ds"]
    dag_id = ctx["dag"].dag_id

    # Alert regardless
    send_drift_alert(verdict, run_date, dag_id)

    # Increment consecutive counter
    current_count = int(Variable.get("drift_consecutive_count", default_var=0))
    new_count = current_count + 1
    Variable.set("drift_consecutive_count", new_count)
    Variable.set("drift_last_detected_date", run_date)
    logger.info(
        "Consecutive drift runs: %d → %d. Last detected: %s",
        current_count, new_count, run_date,
    )

    # Check if we've hit the threshold
    thresholds = load_thresholds()
    required = thresholds.get("consecutive_runs_before_retrain", 3)
    if new_count >= required:
        Variable.set("drift_retrain_requested", "true")
        logger.warning(
            "Retraining threshold reached (%d consecutive runs). "
            "drift_retrain_requested=true",
            new_count,
        )
    else:
        logger.info(
            "Waiting for %d more consecutive drift run(s) before retraining.",
            required - new_count,
        )


# ---------------------------------------------------------------------------
# DAG
# ---------------------------------------------------------------------------
default_args = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": False,
}

with DAG(
    dag_id="drift_monitoring",
    default_args=default_args,
    description="Detect ML data & prediction drift; alert and flag for retraining",
    schedule_interval="0 6 * * *",  # 06:00 UTC daily (after ingestion)
    start_date=days_ago(7),
    catchup=True,
    max_active_runs=1,
    tags=["ml", "drift", "monitoring"],
) as dag:

    load_baseline_task = PythonOperator(
        task_id="load_baseline",
        python_callable=_load_baseline,
    )

    load_recent_task = PythonOperator(
        task_id="load_recent_inference",
        python_callable=_load_recent_inference,
    )

    compute_task = PythonOperator(
        task_id="compute_drift_metrics",
        python_callable=_compute_drift_metrics,
    )

    persist_task = PythonOperator(
        task_id="persist_drift_results",
        python_callable=_persist_drift_results,
    )

    evaluate_task = BranchPythonOperator(
        task_id="evaluate_thresholds",
        python_callable=_evaluate_thresholds,
    )

    alert_task = PythonOperator(
        task_id="send_drift_alert",
        python_callable=_send_drift_alert,
    )

    retrain_flag_task = PythonOperator(
        task_id="flag_for_retraining",
        python_callable=_flag_for_retraining,
    )

    done = EmptyOperator(
        task_id="drift_check_complete",
        trigger_rule="none_failed_min_one_success",
    )

    # Wiring
    [load_baseline_task, load_recent_task] >> compute_task
    compute_task >> persist_task >> evaluate_task
    evaluate_task >> [alert_task, retrain_flag_task, done]
    alert_task >> done
    retrain_flag_task >> done