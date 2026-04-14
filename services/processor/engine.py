"""
SecondGradient Signal Engine - MVP Version

Core processing engine that computes:
- Drift (PSI-based)
- Velocity (rate of change)
- Acceleration (change in velocity)
- Time-to-failure prediction
"""

import time
import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque


@dataclass
class SignalState:
    """State for a single feature's signal processing."""
    values: deque = field(default_factory=lambda: deque(maxlen=100))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=100))
    drift_history: deque = field(default_factory=lambda: deque(maxlen=50))
    velocity_history: deque = field(default_factory=lambda: deque(maxlen=50))
    acceleration_history: deque = field(default_factory=lambda: deque(maxlen=50))

    # Baseline for drift calculation
    baseline_mean: float = 0.0
    baseline_std: float = 1.0
    baseline_count: int = 0

    # EMA smoothing
    ema_drift: float = 0.0
    ema_velocity: float = 0.0
    ema_acceleration: float = 0.0

    initialized: bool = False


class SignalEngine:
    """Core signal processing engine for drift detection and prediction."""

    def __init__(self, window_size: int = 50, alpha: float = 0.1):
        self.window_size = window_size
        self.alpha = alpha  # EMA smoothing factor
        self.states: Dict[str, SignalState] = defaultdict(SignalState)
        self.failure_threshold = 0.25  # PSI threshold for "failure"

    def process_event(self, model: str, features: Dict[str, float], timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        Process a single ML inference event.

        Args:
            model: Model identifier
            features: Feature values
            timestamp: Event timestamp (defaults to current time)

        Returns:
            Processing results with predictions
        """
        if timestamp is None:
            timestamp = time.time()

        results = {}

        for feature_name, value in features.items():
            key = f"{model}:{feature_name}"
            state = self.states[key]

            # Initialize baseline if needed
            if not state.initialized:
                self._initialize_baseline(state, value)
                continue

            # Add new data point
            state.values.append(value)
            state.timestamps.append(timestamp)

            # Compute drift
            drift = self._compute_drift(state, value)
            state.drift_history.append(drift)

            # Apply EMA smoothing to drift
            if len(state.drift_history) == 1:
                state.ema_drift = drift
            else:
                state.ema_drift = self.alpha * drift + (1 - self.alpha) * state.ema_drift

            # Compute velocity (rate of drift change)
            if len(state.drift_history) >= 2:
                velocity = np.diff(list(state.drift_history)[-10:]).mean()  # Last 10 points
                state.velocity_history.append(velocity)

                # EMA smoothing for velocity
                if len(state.velocity_history) == 1:
                    state.ema_velocity = velocity
                else:
                    state.ema_velocity = self.alpha * velocity + (1 - self.alpha) * state.ema_velocity

                # Compute acceleration (change in velocity)
                if len(state.velocity_history) >= 2:
                    acceleration = np.diff(list(state.velocity_history)[-10:]).mean()
                    state.acceleration_history.append(acceleration)

                    # EMA smoothing for acceleration
                    if len(state.acceleration_history) == 1:
                        state.ema_acceleration = acceleration
                    else:
                        state.ema_acceleration = self.alpha * acceleration + (1 - self.alpha) * state.ema_acceleration

            # Store results
            results[feature_name] = {
                "drift": round(state.ema_drift, 4),
                "velocity": round(state.ema_velocity, 6) if state.velocity_history else 0.0,
                "acceleration": round(state.ema_acceleration, 6) if state.acceleration_history else 0.0,
                "samples": len(state.values)
            }

        # Aggregate across features for model-level prediction
        if results:
            model_prediction = self._predict_model_failure(model, results)
            return {
                "model": model,
                "timestamp": timestamp,
                "features": results,
                "prediction": model_prediction
            }

        return {
            "model": model,
            "timestamp": timestamp,
            "status": "initializing",
            "message": "Collecting baseline data"
        }

    def _initialize_baseline(self, state: SignalState, value: float):
        """Initialize baseline statistics."""
        state.baseline_mean = value
        state.baseline_std = max(abs(value) * 0.1, 0.01)  # Small initial std
        state.baseline_count = 1
        state.initialized = True

    def _compute_drift(self, state: SignalState, current_value: float) -> float:
        """Compute PSI-based drift score."""
        # Simple normalized drift (can be upgraded to full PSI)
        if state.baseline_std == 0:
            return 0.0

        z_score = abs(current_value - state.baseline_mean) / state.baseline_std
        drift = min(z_score / 3.0, 1.0)  # Normalize to 0-1 range

        # Update baseline with exponential moving average
        alpha_baseline = 0.01  # Slow baseline adaptation
        state.baseline_mean = alpha_baseline * current_value + (1 - alpha_baseline) * state.baseline_mean
        state.baseline_std = alpha_baseline * abs(current_value - state.baseline_mean) + (1 - alpha_baseline) * state.baseline_std

        return drift

    def _predict_model_failure(self, model: str, feature_results: Dict) -> Dict[str, Any]:
        """Predict time-to-failure for the entire model."""
        # Aggregate across features
        drifts = [r["drift"] for r in feature_results.values()]
        velocities = [r["velocity"] for r in feature_results.values() if r["velocity"] != 0]
        accelerations = [r["acceleration"] for r in feature_results.values() if r["acceleration"] != 0]

        avg_drift = np.mean(drifts) if drifts else 0.0
        avg_velocity = np.mean(velocities) if velocities else 0.0
        avg_acceleration = np.mean(accelerations) if accelerations else 0.0

        # Determine risk level
        risk = "LOW"
        if avg_drift > 0.15:
            risk = "MEDIUM"
        if avg_drift > 0.25 or avg_velocity > 0.01:
            risk = "HIGH"
        if avg_drift > 0.4 or avg_acceleration > 0.001:
            risk = "CRITICAL"

        # Predict time-to-failure
        time_to_failure = self._predict_time_to_failure(avg_drift, avg_velocity, avg_acceleration)

        return {
            "risk": risk,
            "avg_drift": round(avg_drift, 4),
            "avg_velocity": round(avg_velocity, 6),
            "avg_acceleration": round(avg_acceleration, 6),
            "time_to_failure_minutes": time_to_failure,
            "confidence": self._calculate_confidence(feature_results)
        }

    def _predict_time_to_failure(self, drift: float, velocity: float, acceleration: float) -> Optional[int]:
        """Predict minutes until failure threshold is reached."""
        if drift >= self.failure_threshold:
            return 0  # Already at failure

        if velocity <= 0 and acceleration <= 0:
            return None  # Not trending toward failure

        # Linear prediction: solve drift + velocity*t = threshold
        if velocity > 0:
            linear_time = (self.failure_threshold - drift) / velocity
            if linear_time > 0:
                return max(1, int(linear_time * 60))  # Convert to minutes

        # Acceleration-based prediction: solve drift + velocity*t + 0.5*acceleration*t^2 = threshold
        if acceleration > 0:
            a = 0.5 * acceleration
            b = velocity
            c = drift - self.failure_threshold

            discriminant = b**2 - 4*a*c
            if discriminant >= 0:
                t1 = (-b + np.sqrt(discriminant)) / (2*a)
                t2 = (-b - np.sqrt(discriminant)) / (2*a)
                positive_t = max(t for t in [t1, t2] if t > 0)
                if positive_t:
                    return max(1, int(positive_t * 60))

        return None

    def _calculate_confidence(self, feature_results: Dict) -> str:
        """Calculate prediction confidence based on data quality."""
        num_features = len(feature_results)
        avg_samples = np.mean([r["samples"] for r in feature_results.values()])

        if avg_samples < 10 or num_features < 2:
            return "LOW"
        elif avg_samples < 50 or num_features < 3:
            return "MEDIUM"
        else:
            return "HIGH"

    def get_model_state(self, model: str) -> Dict[str, Any]:
        """Get current state for a model."""
        model_states = {}
        for key, state in self.states.items():
            if key.startswith(f"{model}:"):
                feature = key.split(":", 1)[1]
                model_states[feature] = {
                    "drift": round(state.ema_drift, 4),
                    "velocity": round(state.ema_velocity, 6),
                    "acceleration": round(state.ema_acceleration, 6),
                    "samples": len(state.values),
                    "initialized": state.initialized
                }

        return {
            "model": model,
            "features": model_states,
            "feature_count": len(model_states)
        }


# Global engine instance
engine = SignalEngine()