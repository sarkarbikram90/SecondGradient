**Project Architecture — SecondGradient**

This document describes a scalable, modular architecture to implement the product vision in `project-story.md`. It uses a TypeScript frontend, Go backend services (API + orchestration gateway), and Python services for analytics, drift detection, inference pipelines and retraining. The architecture below is opinionated for production readiness (Kubernetes, event bus, object storage, observability, CI/CD).

**Goals**
- Scalable: services independently scale on Kubernetes (HPA).
- Modular: clear separation of concerns between UI (TypeScript), API (Go), and compute/ML (Python).
- Reproducible: containerized services, infra-as-code and CI pipelines.
- Secure: secrets managed outside repo, token-based auth, observability and rate-limiting.

**High-level components**
- Web (`web/`) — TypeScript (Next.js/Vite + React + Tailwind or CSS Modules). Static site + SPA for admin flows.
- API Gateway & Services (`api/`) — Go microservices handling auth, waitlist, admin endpoints, and ingress traffic. Lightweight, fast, and compiled for production.
- Event Bus — Kafka (or Redis Streams for small deployments) for decoupling ingestion from analytics and retraining.
- Object Storage — S3-compatible store (MinIO locally, AWS S3 in cloud) for datasets, artifacts, model binaries and drift artifacts.
- RDS / Postgres — primary relational store for metadata (waitlist, users, jobs, model metadata).
- Python services (`services/python/`) — analytics, drift detection, inference pre-/post-processing, training jobs. Packaged as containers and deployed as Kubernetes Jobs/Deployments. Existing Airflow DAGs become Airflow tasks that either call these services or use KubernetesPodOperator.
- Orchestration — Airflow (control-plane) for scheduled/complex ML workflows and retraining triggers. Use KubernetesExecutor/PodOperator for isolation.
- Model Registry — MLflow (or lightweight registry using Postgres + object storage).
- Observability — Prometheus + Grafana for metrics, OpenTelemetry for tracing, ELK/Elastic or Loki for logging.
- CI/CD — GitHub Actions (or equivalent) to build Docker images, run linters/tests, publish images to registry, and apply helm manifests.

**Mermaid diagram**
```mermaid
flowchart LR
  Browser[(Browser / User)] --> CDN[CDN / Static Hosting]
  CDN --> Frontend[Web App (Next.js, TypeScript)]
  Frontend -->|REST / GraphQL| APIGW[API Gateway / Go Backend]
  APIGW --> Postgres[(Postgres / RDS)]
  APIGW --> MinIO[(S3 / MinIO)]
  APIGW -->|produce| Kafka[(Event Bus: Kafka / Redis Streams)]
  Kafka --> Analytics[Python Analytics Service]
  Kafka --> Drift[Python Drift Service]
  Analytics --> MinIO
  Drift --> MinIO
  Drift --> APIGW
  APIGW -->|trigger| Airflow[Airflow Orchestrator]
  Airflow --> Trainer[Python Trainer / Retraining Job]
  Trainer --> MinIO
  Trainer --> ModelReg[(Model Registry / MLflow)]
  APIGW --> AdminUI[Admin UI (inside Web App)]
  APIGW -->|metrics| Prometheus[Prometheus]
  Analytics -->|metrics| Prometheus
  Drift -->|metrics| Prometheus
  Logs --> ELK[Logging (ELK / Loki)]
  subgraph Infra
    Kubernetes[Kubernetes Cluster]
    ContainerRegistry[(Docker Registry)]
  end
  ContainerRegistry --> Kubernetes
  Kubernetes --> APIGW
  Kubernetes --> Analytics
  Kubernetes --> Drift
  Kubernetes --> Airflow
```

**Data flows (short)**
1. User interacts with the frontend. Waitlist signups and admin actions call the Go API.
2. The Go API validates input, writes metadata to Postgres, stores artifacts to S3 if needed, and publishes events to Kafka.
3. Python analytics/drift services consume Kafka events, compute metrics, store artifacts to S3 and write metric summaries back to Postgres (and expose Prometheus metrics).
4. Airflow (K8s) is used to run heavier retraining jobs (via KubernetesPodOperator), which output models to the model registry and artifacts to S3.
5. The frontend Admin UI reads metadata from the Go API which queries Postgres / Model Registry.

**Mapping from current repo and `project-story.md`**
- `index.html` + inline JS/CSS → move into `web/` TypeScript project. Keep `privacy.html` as static route during migration but port content to `web/`.
- FastAPI waitlist server → port logic to Go `api/waitlist` service (small, fast, static schema). Keep a minimal shim (temporary) so existing frontend POSTs still work during migration.
- Current DAGs (Airflow) and Python analytics code → remain in `services/python/` and be packaged as reusable libraries (e.g., `services/python/secondgradient_core`). Airflow will call these via KubernetesPodOperator or by HTTP/gRPC to Python services.
- SQLite waitlist (local) → Postgres in production. Provide migration script (sqlite → postgres) for live data.
- Object artifacts (currently local ARTIFACT_DIR) → central S3 bucket (MinIO locally). Update DAGs and Python code to read/write S3 URIs and avoid pushing large objects in XCom.

**Repository layout (recommended)**
```
/web                      # TypeScript frontend (Next.js or Vite + React + TS)
/api                      # Go microservices (api gateway, auth, waitlist)
/services/python          # Python packages: analytics, drift, training, common libs
/infra                    # Terraform / k8s / helm charts
/charts                   # Helm charts for deployment
/ci                       # CI workflows and scripts (GitHub Actions)
/site                     # legacy static content (temporary)
README.md
project-architecture-diagram.md
```

**Concrete repo changes needed**
1. Create `web/` and scaffold a TypeScript app. Move the landing page and privacy page into `web/` and convert UI to React components. Add TypeScript, ESLint, Prettier, and unit test setup (Vitest/Jest).
2. Create `api/` (Go):
   - `api/waitlist` exposes POST /v1/waitlist and GET /v1/admin/waitlist.
   - `api/auth` provides token validation and admin management (JWT/OAuth). Use middleware for rate-limiting and CORS.
   - Provide protobuf / OpenAPI specs for API contracts.
3. Replace local SQLite with Postgres for production and add migrations (e.g., embed `migrations/` with goose or golang-migrate for Go, and Alembic for Python where needed).
4. Move Python analytics code into `services/python/` with proper packaging (pyproject.toml), unit tests, and Dockerfile. Use the same logic as existing DAGs but expose functionality as CLI and HTTP/gRPC endpoints as appropriate.
5. Add an Event Bus (Kafka) and update producers/consumers: Go API produces events, Python services consume. For a simpler initial setup, Redis Streams can be used.
6. Add object storage integration (MinIO) and update code to treat artifacts as URIs. Modify DAGs and Python code to use boto3/minio to read/write artifacts.
7. Add Helm charts and k8s manifests for deployments and a `docker-compose.dev.yml` for local dev (Postgres, MinIO, Kafka/Redis, Airflow, api service).
8. Add CI workflows: tests, lint, security scans (bandit, pip-audit, gosec), build images and push to registry, and optionally run integration tests via kind/k3d.

**Security & operations**
- Use Kubernetes secrets or HashiCorp Vault for secret management; never commit secrets.
- Mutual TLS (mTLS) for service-to-service auth where possible, or mTLS + JWT.
- Rate limiting, input validation, and logging.
- Audit and access controls for admin endpoints.

**Observability**
- Expose Prometheus metrics from Go and Python services. Scrape them in Prometheus and build dashboards in Grafana.
- Tracing with OpenTelemetry (Go + Python) and a tracing backend (Jaeger).
- Centralized logging to ELK or Loki.

**Migration / Implementation plan (phased)**
Phase 0 — Safety & infra (1–2 days):
- Add Postgres + MinIO + Kafka to `docker-compose.dev.yml` for local dev.
- Keep current Airflow and DAGs working against MinIO.

Phase 1 — Minimal MVP (3–7 days):
- Scaffold `web/` and port `index.html` (static) to React + TypeScript.
- Implement `api/waitlist` in Go, point frontend to it, and migrate data from SQLite to Postgres.
- Containerize services and add dev docker-compose for local testing.

Phase 2 — Analytics & drift (5–10 days):
- Package Python analytics and drift code into `services/python/` with tests and Docker images.
- Wire Kafka events and make Python consumers process events and write metrics/artifacts to MinIO/Postgres.
- Add Airflow k8s integration for retraining jobs (or keep Airflow and run KubernetesPodOperator).

Phase 3 — Production hardening (7–14 days):
- Add CI/CD, Helm charts, security scanning (gosec, bandit, pip-audit), and deploy to a Kubernetes environment (staging).
- Add monitoring and tracing dashboards, autoscaling rules, and run load tests.

**Minimal dev commands & scaffolding**
1. Scaffold web (example using Vite + React + TS):
```bash
cd web
npm create vite@latest . --template react-ts
npm install
```
2. Scaffold Go module for API:
```bash
mkdir api && cd api
go mod init github.com/yourorg/secondgradient/api
```
3. Scaffold Python package for analytics:
```bash
mkdir -p services/python/secondgradient_core
cd services/python/secondgradient_core
python -m venv .venv
pip install -e .
```

**Notes / tradeoffs**
- Using Go for the API gives great performance for the gateway but increases the language surface area (Go + Python + TypeScript). This is acceptable when the team has Go skills; otherwise consider Node.js for faster developer iteration.
- Kafka provides high throughput and guarantees; for smaller deployments prefer Redis Streams to reduce operational overhead.

---
This file should be used as the canonical architecture proposal. I will now create a feature branch and commit this file so we can iterate with PRs. If you want, I can scaffold `web/`, `api/`, and `services/python/` skeletons next and add CI workflows.
