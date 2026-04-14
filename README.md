# SecondGradient

**Predictive Intelligence for ML Systems**

SecondGradient is a real-time system that understands how ML systems evolve over time. It doesn't just monitor — it predicts failure trajectories, fuses multi-layer signals, and provides actionable intelligence before incidents occur.

---

## The Problem

Traditional ML monitoring fails because it reacts too late:

- **Threshold-based alerts** trigger after degradation is visible
- **Batch pipelines** can't catch accelerating drift in real-time
- **Siloed signals** miss correlations between data, model, and infrastructure
- **Static metrics** ignore the dynamics of system health

In production ML, failures don't happen instantly — they accelerate silently. By the time thresholds are breached, it's often too late for graceful intervention.

---

## The Core Idea

SecondGradient tracks the **second derivative** of ML system health:

- **Drift**: How much has the system changed?
- **Velocity**: How fast is it changing?
- **Acceleration**: How fast is the rate of change itself changing?

This enables **trajectory prediction** — estimating when failures will occur, not just detecting that they might.

---

## Architecture Overview

SecondGradient is built as a streaming-first system:

1. **Ingestion Layer**: Kafka streams ML events in real-time
2. **Stream Processor**: PyFlink maintains state and computes drift, velocity, acceleration
3. **Signal Engine**: Applies smoothing, filtering, and statistical analysis
4. **Prediction Engine**: Solves for time-to-failure using trajectory modeling
5. **Fusion Engine**: Combines data, model, and infra signals with correlation boosts
6. **Root Cause Engine**: Classifies issues as DATA, MODEL, INFRA, or EARLY WARNING
7. **API Layer**: FastAPI exposes real-time insights
8. **Frontend**: Next.js dashboard for visualization

---

## Key Differentiators

| Traditional Monitoring | SecondGradient |
| ---------------------- | -------------- |
| Reactive alerts after thresholds | Predictive insights before failure |
| Static metrics and snapshots | Trajectory modeling with velocity/acceleration |
| Batch processing (daily/hourly) | Real-time streaming with sub-second latency |
| Single-layer signals | Multi-signal fusion across data/model/infra |
| Threshold-based decisioning | Trajectory-based prediction |

---

## System Components

### Services

- **ingestion/**: Kafka producer agents that stream ML events
- **stream-processor/**: PyFlink job for real-time signal processing
- **api/**: FastAPI service exposing /signals, /risk, /prediction, /root-cause
- **frontend/**: Next.js dashboard with real-time graphs and alerts

### Libraries

- **drift/**: PSI, KL-divergence, and distribution shift calculations
- **signals/**: EMA smoothing, z-score filtering, rolling statistics
- **prediction/**: Linear and acceleration-based trajectory solvers
- **fusion/**: Signal normalization, weighted fusion, correlation analysis

### Infrastructure

- **docker/**: Container definitions for all services
- **terraform/**: Cloud infrastructure provisioning
- **k8s/**: Kubernetes manifests for production deployment

---

## Quick Start (MVP Demo)

SecondGradient MVP demonstrates real-time drift acceleration detection and time-to-failure prediction.

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)

### Run the Full Demo

```bash
# Clone and setup
git clone https://github.com/yourorg/secondgradient.git
cd secondgradient

# Start all services
docker compose up --build

# This brings up:
# - API (FastAPI backend) on http://localhost:8000
# - Frontend (Next.js dashboard) on http://localhost:3000
# - Simulator (generates test data)
```

### Manual Testing

Send a test ML event:

```bash
curl -X POST http://localhost:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rec-v1",
    "features": {
      "user_age": 35.2,
      "item_category": 0.7,
      "session_length": 120.5
    },
    "prediction": 0.85
  }'
```

Check current predictions:

```bash
curl http://localhost:8000/api/predictions
```

### Run Simulator for Demo Data

```bash
# Normal operation (baseline)
python examples/simulator/simulator.py --mode normal --duration 30

# Gradual drift
python examples/simulator/simulator.py --mode drift --duration 60

# Accelerating failure (triggers predictions)
python examples/simulator/simulator.py --mode failure --model rec-v1
```

### Validate the Demo

Run the integration test to ensure everything works:

```bash
python test_mvp.py
```

This tests:
- ✅ API health and responsiveness
- ✅ ML event ingestion
- ✅ Real-time predictions generation
- ✅ Frontend connectivity

---

## Example Output

```
⚠ EARLY WARNING DETECTED
Root Cause: DATA DRIFT
Failure predicted in 87 minutes
Confidence: HIGH
Signals: velocity=+0.12, acceleration=+0.03
```

---

## Technology Stack (MVP)

- **Backend**: Python (FastAPI, NumPy, Pydantic)
- **Processing**: In-memory signal engine with sliding windows and EMA smoothing
- **Frontend**: TypeScript (Next.js + Tailwind CSS + Chart.js)
- **Storage**: In-memory state (SQLite fallback for persistence)
- **Containerization**: Docker + Docker Compose
- **Data Simulation**: Python scripts for controlled drift patterns

---

## Roadmap

- **Q2 2026**: ML-based signal fusion and anomaly detection
- **Q3 2026**: Auto-remediation hooks (retraining, traffic shifting)
- **Q4 2026**: Multi-tenant SaaS platform
- **2027**: Enterprise integrations (Datadog, New Relic, etc.)

---

## Philosophy

SecondGradient exists to make ML systems predictable. It transforms monitoring from a reactive necessity into a proactive intelligence layer. By understanding system trajectories, not just states, it gives engineers the time and context to act before failures impact users.

---

## Contributing

This is a foundational system for a new category of ML infrastructure. Contributions welcome in:

- Streaming processing optimizations
- Prediction algorithm improvements
- Frontend visualization enhancements
- Infrastructure automation

See `docs/` for detailed architecture and API specs.
