# SecondGradient API Specification

## Overview

The SecondGradient API provides real-time access to predictive intelligence for ML systems.

Base URL: `http://localhost:8000/api`

## Endpoints

### GET /signals/{model}

Get current signal state for a model.

**Response:**
```json
{
  "model": "rec-v3",
  "timestamp": 1640995200,
  "drift": 0.12,
  "velocity": 0.03,
  "acceleration": 0.001,
  "smoothed_drift": 0.11,
  "features": {
    "user_age": 0.08,
    "item_category": 0.15
  }
}
```

### GET /risk/{model}

Get current risk assessment.

**Response:**
```json
{
  "model": "rec-v3",
  "overall_risk": "warning",
  "confidence": 0.87,
  "signals": ["data_drift", "velocity_increase"],
  "last_updated": 1640995200
}
```

### GET /prediction/{model}

Get failure prediction.

**Response:**
```json
{
  "model": "rec-v3",
  "failure_predicted": true,
  "minutes_remaining": 87,
  "confidence": "HIGH",
  "method": "combined",
  "trajectory": {
    "current_drift": 0.12,
    "velocity": 0.03,
    "acceleration": 0.001
  }
}
```

### GET /root-cause/{model}

Get root cause analysis.

**Response:**
```json
{
  "model": "rec-v3",
  "root_cause": "DATA_DRIFT",
  "confidence": 0.92,
  "contributing_factors": [
    {"feature": "user_age", "drift": 0.15, "impact": "high"},
    {"feature": "item_category", "drift": 0.08, "impact": "medium"}
  ],
  "recommendations": [
    "Monitor user_age distribution",
    "Consider retraining if drift persists"
  ]
}
```

### POST /events

Ingest ML event (used by ingestion service).

**Request:**
```json
{
  "model": "rec-v3",
  "timestamp": 1640995200,
  "features": {"user_age": 25, "item_category": "electronics"},
  "prediction": 0.87,
  "metadata": {"latency": 120, "version": "v1.2"}
}
```

**Response:**
```json
{"status": "accepted", "event_id": "abc-123"}
```

### GET /health

Service health check.

**Response:**
```json
{"status": "healthy", "timestamp": 1640995200}
```

## Authentication

Use API key in header: `X-API-Key: your-key-here`

## Rate Limits

- 1000 requests/minute per IP
- 10000 requests/minute per API key

## Error Responses

```json
{
  "error": "ModelNotFound",
  "message": "Model 'unknown-model' not found",
  "timestamp": 1640995200
}
```