# SecondGradient

<p align="center">
  <img src="assets/SecondGradient-logo.png" alt="SecondGradient logo" width="280" />
</p>

**Predictive intelligence for production ML systems**

SecondGradient is designed to surface early-warning signals across the entire ML lifecycle. It is not a generic monitoring dashboard — it is a production-grade pipeline for ingesting inference data, validating quality, computing drift metrics, evaluating risk, and triggering alerts or retraining decisions.

---

## Repository Overview

This repository contains two primary aspects:

1. **Marketing and waitlist site** — the landing page, branding, and early-access service.
2. **ML reliability pipeline** — Airflow orchestration, drift metric libraries, validators, alerting utilities, and retraining workflow.

### Key folders

- `index.html` — main landing page for SecondGradient.
- `assets/` — brand assets including the logo.
- `configs/` — YAML threshold configuration for drift decisions.
- `dags/` — Airflow DAGs for ingestion, drift monitoring, and retraining orchestration.
- `src/` — core Python libraries for data loaders, validators, drift analysis, and alerting.
- `site/` — FastAPI waitlist server, privacy page, and site assets.
- `docker-compose.yaml` — local development environment for Airflow and the waitlist service.
- `requirements.txt` — runtime dependencies.
- `requirements-dev.txt` — developer and testing dependencies.
- `project-architecture-diagram.md` — architecture reference diagram.

---

## System Architecture

SecondGradient is built around a staged workflow that mimics production ML operations:

1. **Inference ingestion and validation**
   - Raw predictions are ingested from `RAW_INFERENCE_DIR`.
   - Schemas are enforced with `src/data/validators.py`.
   - Data is persisted as date-partitioned snapshots.

2. **Drift calculation and evaluation**
   - Baseline statistics are loaded from `BASELINE_PATH`.
   - Current inference snapshots are compared to baseline using PSI and KS tests.
   - Mean and variance shift are computed for numerical features.
   - Drift results are stored and summarized.

3. **Decisioning and notification**
   - `src/drift/thresholds.py` interprets drift metrics against configurable thresholds.
   - The system determines whether to alert, continue monitoring, or trigger retraining.
   - Slack alerts are sent via `src/alerts/slack.py`.

4. **Retraining orchestration**
   - The retraining DAG checks business rules and drift history.
   - A training dataset is assembled from recent snapshots.
   - The system records model metadata and resets drift counters.

---

## Codebase Breakdown

### `src/data`

- `loaders.py`
  - Load baseline statistics and inference snapshots.
  - Supports `parquet`, `csv`, and `json`.
  - Saves validated snapshots as date-partitioned files.

- `validators.py`
  - Defines `SchemaSpec` and `ValidationResult`.
  - Validates column presence, numeric types, and null rates.
  - Raises actionable errors for Airflow tasks.

### `src/drift`

- `ks_test.py`
  - Computes Kolmogorov-Smirnov tests for distribution drift.
  - Generates feature-level drift summaries.

- `psi.py`
  - Computes Population Stability Index for feature stability.
  - Classifies drift severity as `ok`, `warning`, or `critical`.

- `thresholds.py`
  - Loads threshold config from `configs/drift_thresholds.yaml`.
  - Implements `DriftDecisionEngine` to aggregate metric verdicts.
  - Decides whether to alert or recommend retraining.

### `src/alerts`

- `slack.py`
  - Sends formatted alerts to Slack using webhook payloads.
  - Provides drift-specific formatting for severity and field details.

- `email.py` and `MS_Teams.py`
  - Present as integration placeholders for future notification channels.

---

## Airflow Workflow

### `dags/inference_ingestion.py`

- Loads raw inference data for the scheduled date.
- Validates schema and snapshot quality.
- Saves validated snapshots under `SNAPSHOT_DIR`.
- Branches for missing or late data.

### `dags/drift_monitoring.py`

- Loads baseline and recent inference snapshots.
- Computes PSI, KS, and mean/variance shift metrics.
- Persists drift metrics and JSON reports.
- Evaluates drift against thresholds.
- Sends Slack alerts or flags retraining.

### `dags/retraining_trigger.py`

- Verifies retraining conditions and business hours.
- Assembles a training dataset from recent snapshots.
- Triggers retraining and logs model version metadata.
- Resets drift counters after retraining begins.

---

## Waitlist Site and API

The `site/server` FastAPI service provides a lightweight waitlist API:

- `POST /api/waitlist` — add early access entries.
- `GET /api/admin/waitlist` — admin access with `WAITLIST_ADMIN_TOKEN`.
- `GET /privacy` — serves the privacy page.

The site also includes static assets and the landing page experience built in `index.html`.

---

## Configuration

Primary configuration is managed through environment variables and YAML files.

Important settings:

- `RAW_INFERENCE_DIR` — source for raw inference logs.
- `SNAPSHOT_DIR` — destination for validated snapshots.
- `BASELINE_PATH` — baseline statistics for drift comparison.
- `DRIFT_RESULTS_DIR` — output folder for drift metrics and reports.
- `MODEL_REGISTRY_DIR` — location for retraining metadata.
- `DRIFT_CONFIG_PATH` — path to drift thresholds YAML.
- `SLACK_WEBHOOK_URL` — Slack incoming webhook URL.
- `WAITLIST_ADMIN_TOKEN` — admin token for waitlist API.
- `WAITLIST_DB` — sqlite database path for the waitlist service.

Configuration defaults are defined in code and can be overridden by environment variables.

---

## Local Development

### Run the site service

```bash
cd site/server
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Run with Docker Compose

```bash
cp .env.template .env
# populate .env with POSTGRES_PASSWORD, REDIS_PASSWORD, AIRFLOW__CORE__FERNET_KEY, WAITLIST_ADMIN_TOKEN

docker compose up --build
```

This brings up:

- `postgres`
- `redis`
- `airflow-webserver`
- `airflow-scheduler`
- `airflow-worker`
- `airflow-triggerer`
- `waitlist`

---

## Project Workflow

1. **Ingest raw predictions** into the Airflow ingestion DAG.
2. **Validate snapshot quality** and persist the data.
3. **Compute drift metrics** for prediction distributions and feature shifts.
4. **Evaluate risk** using threshold-driven decision logic.
5. **Alert or retrain** based on the severity of drift.
6. **Log model metadata** and reset counters after retraining.

---

## Project Status

SecondGradient is an active development prototype for predictive ML observability. Current work focuses on:

- improving drift aggregation and risk scoring
- expanding integration support for Prometheus, Kafka, Flink, and CLI workflows
- implementing real training orchestration logic
- adding dashboard and visualization layers
- hardening Airflow and production deployment

---

## Contribution Guide

Contributions are welcome, especially in these areas:

- add functional notification channels (email, Teams, PagerDuty)
- implement retraining job submission to a real training platform
- extend schema validation and ingestion coverage
- improve UI and waitlist experience
- harden config management and pipeline reliability

---

## Architecture Reference

See `project-architecture-diagram.md` for a visual architecture overview and component relationships.

---

## Philosophy

SecondGradient exists to make ML systems less reactive and more predictive. It is built to:

- track the shape of change, not just static values
- catch accelerating degradation before incidents
- correlate signals across data, model, and infra layers
- provide engineers with context, not just noise
