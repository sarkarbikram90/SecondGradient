import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from .db import get_connection, format_timestamp


def save_event(model: str, timestamp: float, features: Dict[str, Any], prediction: Optional[float]):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO events (model, timestamp, features, prediction) VALUES (?, ?, ?, ?)",
            (model, format_timestamp(timestamp), json.dumps(features), prediction),
        )
        conn.commit()
        return cursor.lastrowid


def get_events(model: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if model:
            cursor.execute(
                "SELECT * FROM events WHERE model = ? ORDER BY timestamp DESC LIMIT ?",
                (model, limit),
            )
        else:
            cursor.execute(
                "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        rows = cursor.fetchall()

    return [
        {
            "id": row["id"],
            "model": row["model"],
            "timestamp": row["timestamp"],
            "features": json.loads(row["features"]),
            "prediction": row["prediction"],
        }
        for row in rows
    ]


def save_signal(model: str, feature: str, drift: float, velocity: float, acceleration: float, timestamp: float):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO signals (model, feature, drift, velocity, acceleration, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (model, feature, drift, velocity, acceleration, format_timestamp(timestamp)),
        )
        conn.commit()
        return cursor.lastrowid


def get_signals(model: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if model:
            cursor.execute(
                "SELECT * FROM signals WHERE model = ? ORDER BY timestamp DESC LIMIT ?",
                (model, limit),
            )
        else:
            cursor.execute(
                "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        rows = cursor.fetchall()

    return [
        {
            "id": row["id"],
            "model": row["model"],
            "feature": row["feature"],
            "drift": row["drift"],
            "velocity": row["velocity"],
            "acceleration": row["acceleration"],
            "timestamp": row["timestamp"],
        }
        for row in rows
    ]


def save_prediction(model: str, risk: str, time_to_failure: Optional[float], confidence: str, root_cause: str, timestamp: float):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO predictions (model, risk, time_to_failure, confidence, root_cause, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (model, risk, time_to_failure, confidence, root_cause, format_timestamp(timestamp)),
        )
        conn.commit()
        return cursor.lastrowid


def get_latest_prediction(model: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if model:
            cursor.execute(
                "SELECT * FROM predictions WHERE model = ? ORDER BY timestamp DESC LIMIT 1",
                (model,),
            )
        else:
            cursor.execute(
                "SELECT * FROM predictions ORDER BY timestamp DESC LIMIT 1"
            )
        row = cursor.fetchone()

    if not row:
        return None

    return {
        "id": row["id"],
        "model": row["model"],
        "risk": row["risk"],
        "time_to_failure": row["time_to_failure"],
        "confidence": row["confidence"],
        "root_cause": row["root_cause"],
        "timestamp": row["timestamp"],
    }


def get_prediction_history(model: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if model:
            cursor.execute(
                "SELECT * FROM predictions WHERE model = ? ORDER BY timestamp DESC LIMIT ?",
                (model, limit),
            )
        else:
            cursor.execute("SELECT * FROM predictions ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()

    return [
        {
            "id": row["id"],
            "model": row["model"],
            "risk": row["risk"],
            "time_to_failure": row["time_to_failure"],
            "confidence": row["confidence"],
            "root_cause": row["root_cause"],
            "timestamp": row["timestamp"],
        }
        for row in rows
    ]
