"""
Prediction engine for trajectory modeling and time-to-failure estimation.

Implements:
- Linear prediction
- Acceleration-based prediction
- Time-to-threshold solver
"""

import numpy as np
from typing import List, Optional
from datetime import datetime, timedelta


class TrajectoryPredictor:
    """Predicts failure trajectories based on drift, velocity, acceleration."""

    def __init__(self, threshold: float = 0.25):
        self.threshold = threshold  # PSI threshold for "failure"

    def predict_linear(self, drift_history: List[float], timestamps: List[int]) -> Optional[float]:
        """
        Linear extrapolation of drift to predict when it hits threshold.

        Returns: minutes until threshold, or None if not approaching.
        """
        if len(drift_history) < 2:
            return None

        # Fit linear model: drift = a * t + b
        t = np.array(timestamps)
        d = np.array(drift_history)

        # Normalize timestamps to minutes from now
        t_minutes = (t - t[-1]) / 60.0

        coeffs = np.polyfit(t_minutes, d, 1)
        a, b = coeffs  # drift = a * minutes + b

        if a <= 0:  # Not increasing
            return None

        # Solve: threshold = a * minutes + b
        minutes_to_threshold = (self.threshold - b) / a

        return max(0, minutes_to_threshold)

    def predict_acceleration(self,
                           drift_history: List[float],
                           velocity_history: List[float],
                           acceleration_history: List[float]) -> Optional[float]:
        """
        Acceleration-based prediction using kinematic equations.

        Returns: minutes until threshold.
        """
        if len(acceleration_history) < 1:
            return None

        current_drift = drift_history[-1]
        current_velocity = velocity_history[-1]
        current_acceleration = acceleration_history[-1]

        if current_acceleration <= 0:
            return None  # Not accelerating toward failure

        # Solve quadratic: drift + velocity*t + 0.5*acceleration*t^2 = threshold
        # Rearrange: 0.5*acceleration*t^2 + velocity*t + (drift - threshold) = 0

        a = 0.5 * current_acceleration
        b = current_velocity
        c = current_drift - self.threshold

        discriminant = b**2 - 4*a*c

        if discriminant < 0:
            return None  # No real solution

        # Take positive root
        t1 = (-b + np.sqrt(discriminant)) / (2*a)
        t2 = (-b - np.sqrt(discriminant)) / (2*a)

        t_positive = max(t1, t2) if t1 > 0 or t2 > 0 else None

        return t_positive if t_positive and t_positive > 0 else None

    def predict_failure_time(self,
                           drift_history: List[float],
                           velocity_history: List[float],
                           acceleration_history: List[float],
                           timestamps: List[int]) -> Dict[str, Any]:
        """
        Main prediction method combining linear and acceleration models.

        Returns dict with prediction details.
        """

        linear_pred = self.predict_linear(drift_history, timestamps)
        accel_pred = self.predict_acceleration(drift_history, velocity_history, acceleration_history)

        # Use the more conservative (earlier) prediction
        predictions = [p for p in [linear_pred, accel_pred] if p is not None]
        if not predictions:
            return {
                "failure_predicted": False,
                "minutes_remaining": None,
                "confidence": "LOW",
                "method": None
            }

        minutes_remaining = min(predictions)
        confidence = "HIGH" if len(predictions) == 2 else "MEDIUM"

        return {
            "failure_predicted": True,
            "minutes_remaining": round(minutes_remaining, 1),
            "confidence": confidence,
            "method": "combined" if len(predictions) == 2 else "linear" if linear_pred else "acceleration"
        }


def predict_failure_time(drift_history: List[float],
                        velocity: float,
                        acceleration: float,
                        threshold: float = 0.25) -> Optional[float]:
    """
    Simplified prediction for streaming processor.

    Returns minutes to failure or None.
    """
    predictor = TrajectoryPredictor(threshold)

    # Mock timestamps (assume 1-minute intervals)
    timestamps = list(range(len(drift_history)))

    # Mock velocity/acceleration history
    vel_history = [velocity] * len(drift_history)
    accel_history = [acceleration] * len(drift_history)

    result = predictor.predict_failure_time(
        drift_history, vel_history, accel_history, timestamps
    )

    return result["minutes_remaining"] if result["failure_predicted"] else None