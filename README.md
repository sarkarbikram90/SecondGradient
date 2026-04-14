# SecondGradient

<p align="center">
  <img src="assets/SecondGradient-logo.png" alt="SecondGradient logo" width="260" />
</p>

**Predictive intelligence for production ML systems**

SecondGradient is a research-backed ML reliability framework that detects accelerating degradation across data, model, and infrastructure signals. It is designed to surface warnings early, correlate root causes, and support automatic remediation decisions.

---

## Repository Overview

This repository contains the landing page, website waitlist service, Airflow orchestration, drift detection libraries, alerting utilities, and configuration for a production-oriented ML observability workflow.

### Top-level layout

- `index.html` — marketing landing page with predictive intelligence messaging
- `assets/` — brand assets, including `SecondGradient-logo.png`
- `configs/` — YAML thresholds and runtime config values
- `dags/` — Airflow DAGs for ingestion, drift detection, and retraining orchestration
- `src/` — core Python libraries for data ingestion, validation, drift metrics, and alerts
- `site/` — waitlist server, privacy page, and static site assets
- `docker-compose.yaml` — local development + Airflow orchestration
- `requirements.txt` — production Python dependencies
- `requirements-dev.txt` — developer/test tooling

---

## What SecondGradient Is

SecondGradient is not a dashboard-first monitoring tool. It is a pipeline for:

- capturing inference data and baseline statistics
- validating production snapshot quality
- computing drift and stability metrics
- evaluating risk against configurable thresholds
- alerting and triggering retraining when degradation accelerates

The project is centered on the idea that the second derivative of system health is more predictive than static thresholds.

---

## Core Components

### `src/data`

- `loaders.py` — handles baseline and inference snapshot ingestion
  - supports `parquet`, `csv`, and `json`
  - saves date-partitioned snapshots
  - aggregates recent inference history for drift analysis
- `validators.py` — schema and quality checks for inference snapshots
  - required columns, numeric type enforcement, null-rate checks
  - produces descriptive verdicts for Airflow task failures

### `src/drift`

- `ks_test.py` — Kolmogorov-Smirnov drift testing per feature
- `psi.py` — Population Stability Index calculation
- `thresholds.py` — YAML-driven drift thresholds and decision engine
  - evaluates PSI, KS, mean shift, and variance shift
  - decides whether to alert or mark retraining

### `src/alerts`

- `slack.py` — Slack webhook alerting with severity formatting
  - sends rich drift alerts with feature verdicts
- `email.py` — placeholder for future email notification support
- `MS_Teams.py` — placeholder for Microsoft Teams integration

---

## Airflow Workflow

The `dags/` folder defines the core pipeline in three stages:

### 1. `inference_data_ingestion.py`

- checks for raw inference logs for the logical date
- loads CSV/Parquet/JSON prediction records
- validates schema via `src/data/validators.py`
- persists date-partitioned snapshots under `SNAPSHOT_DIR`
- handles late data cleanly via an Airflow branch

### 2. `drift_monitoring.py`

- loads baseline statistics and recent inference snapshots
- computes drift metrics using `src/drift/psi.py` and `src/drift/ks_test.py`
- computes mean/variance shift over feature distributions
- persists detailed drift reports and parquet artifacts
- evaluates results with `DriftDecisionEngine`
- branches to alerting or retraining flags

### 3. `retraining_trigger.py`

- checks whether retraining conditions are met
- prepares a fresh training dataset from recent snapshots
- triggers retraining logic (currently simulated)
- logs new model version metadata in `MODEL_REGISTRY_DIR`
- resets drift counters after retraining is initiated

---

## Site and Waitlist Service

The `site/` directory contains the landing page assets and a small FastAPI waitlist service.

### `site/server`

- `main.py` — FastAPI app exposing:
  - `POST /api/waitlist`
  - `GET /api/admin/waitlist`
- `db.py` — SQLite-backed waitlist storage
- `models.py` — request/response Pydantic models
- `privacy.html` — privacy page served by the waitlist app

The landing page itself is `index.html` at the repository root.

---

## Configuration

Configuration is driven by environment variables and YAML:

- `DRIFT_CONFIG_PATH` — path to drift threshold YAML
- `SNAPSHOT_DIR`, `BASELINE_PATH` — input/output storage locations
- `RAW_INFERENCE_DIR` — raw inference log source
- `DRIFT_RESULTS_DIR` — output folder for drift artifacts
- `MODEL_REGISTRY_DIR` — model metadata registry path
- `SLACK_WEBHOOK_URL` — Slack alert webhook
- `WAITLIST_ADMIN_TOKEN` — waitlist admin API token
- `WAITLIST_DB` — waitlist SQLite path

The default thresholds file is `configs/drift_thresholds.yaml`.

---

## Local Development

### Option 1: Run the waitlist service

```bash
cd site/server
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Option 2: Run the full stack with Docker Compose

```bash
cp .env.template .env
# update .env with POSTGRES_PASSWORD, REDIS_PASSWORD, AIRFLOW_CORE_FERNET_KEY, WAITLIST_ADMIN_TOKEN

docker compose up --build
```

The Docker Compose setup includes:

- `postgres` database
- `redis` broker
- `airflow-webserver`, `airflow-scheduler`, `airflow-worker`, `airflow-triggerer`
- optional `flower`
- `waitlist` FastAPI service

---

## How to Use

1. Populate raw inference data into `RAW_INFERENCE_DIR` using date-named files like `2024-07-15.parquet`.
2. Configure baseline statistics in `BASELINE_PATH`.
3. Start Airflow and let `inference_data_ingestion` create validated snapshots.
4. `drift_monitoring` computes predictive drift signals and decides whether to alert or retrain.
5. If retraining is required, `retraining_trigger` assembles data and logs model metadata.

---

## Project Status

This repository is an active prototype and support stack for predictive ML observability. Key priorities are:

- improving drift metric fusion and risk scoring
- expanding alerting channels beyond Slack
- adding real retraining integration paths
- exposing richer dashboard/visualization workflows
- hardening Airflow production deployment

---

## Contribution Guidelines

Contributions are welcome. Good first steps include:

- adding functional email or Teams alerts
- implementing real retraining submission logic
- improving schema coverage and snapshot ingestion
- extending `site/` with a production-ready dashboard
- refining risk scoring and drift acceleration logic

---

## Philosophy

SecondGradient is built for engineers who want to act before incidents become incidents. It is focused on:

- predicting degradation trajectories, not waiting for thresholds
- correlating signals across data, model, and infra
- providing actionable root cause context
- making observability an early-warning system rather than a post-mortem tool
