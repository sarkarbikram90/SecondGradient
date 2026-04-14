"""
Streaming processor for SecondGradient using PyFlink.

Maintains state per (model, feature) and computes:
- Drift (PSI/KL)
- Velocity (rate of change)
- Acceleration (second derivative)
- Signal smoothing (EMA)
"""

from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import FlinkKafkaConsumer
from pyflink.datastream.functions import MapFunction, KeyedProcessFunction
from pyflink.common.typeinfo import Types
from pyflink.datastream.state import ValueStateDescriptor
import json
from typing import Dict, Any
from datetime import datetime
import numpy as np

# Import our libs
from libs.drift.psi import compute_psi
from libs.signals.ema import exponential_moving_average
from libs.prediction.trajectory import predict_failure_time


class SignalProcessor(KeyedProcessFunction):
    """Processes streaming ML events and maintains signal state."""

    def __init__(self):
        self.signal_state = None
        self.baseline_state = None

    def open(self, runtime_context):
        self.signal_state = runtime_context.get_state(
            ValueStateDescriptor("signals", Types.PICKLED_BYTE_ARRAY())
        )
        self.baseline_state = runtime_context.get_state(
            ValueStateDescriptor("baseline", Types.PICKLED_BYTE_ARRAY())
        )

    def process_element(self, event: Dict[str, Any], ctx, out):
        model = event["model"]
        timestamp = event["timestamp"]
        features = event["features"]
        prediction = event["prediction"]

        # Get current state
        signals = self.signal_state.value() or {
            "drift_history": [],
            "velocity_history": [],
            "acceleration_history": [],
            "timestamps": []
        }

        baseline = self.baseline_state.value() or self._initialize_baseline(features)

        # Compute drift for each feature
        drift_scores = {}
        for feature, value in features.items():
            if feature in baseline:
                drift = compute_psi([baseline[feature]], [value])
                drift_scores[feature] = drift

        # Compute velocity (rate of drift change)
        if len(signals["drift_history"]) > 1:
            velocity = np.diff(signals["drift_history"][-10:]).mean()  # last 10 points
        else:
            velocity = 0.0

        # Compute acceleration (change in velocity)
        if len(signals["velocity_history"]) > 1:
            acceleration = np.diff(signals["velocity_history"][-10:]).mean()
        else:
            acceleration = 0.0

        # Apply EMA smoothing
        smoothed_drift = exponential_moving_average(drift_scores.values(), alpha=0.1)

        # Predict failure time
        failure_prediction = predict_failure_time(
            drift_history=signals["drift_history"],
            velocity=velocity,
            acceleration=acceleration
        )

        # Update state
        signals["drift_history"].append(smoothed_drift)
        signals["velocity_history"].append(velocity)
        signals["acceleration_history"].append(acceleration)
        signals["timestamps"].append(timestamp)

        # Keep only recent history (last 100 points)
        for key in signals:
            if isinstance(signals[key], list):
                signals[key] = signals[key][-100:]

        self.signal_state.update(signals)

        # Output processed signal
        output = {
            "model": model,
            "timestamp": timestamp,
            "drift": smoothed_drift,
            "velocity": velocity,
            "acceleration": acceleration,
            "failure_prediction_minutes": failure_prediction,
            "features": drift_scores
        }

        out.collect(json.dumps(output))

    def _initialize_baseline(self, features: Dict) -> Dict:
        """Initialize baseline from first event."""
        baseline = {}
        for feature, value in features.items():
            if isinstance(value, (int, float)):
                baseline[feature] = [value]  # Start with single value
        return baseline


def create_stream_processor():
    """Create and configure the Flink streaming job."""

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(4)

    # Kafka consumer
    kafka_props = {
        "bootstrap.servers": "localhost:9092",
        "group.id": "secondgradient-processor"
    }

    kafka_consumer = FlinkKafkaConsumer(
        topics="ml-events",
        deserialization_schema=SimpleStringSchema(),
        properties=kafka_props
    )

    # Parse JSON events
    stream = env.add_source(kafka_consumer) \
        .map(lambda x: json.loads(x)) \
        .key_by(lambda x: f"{x['model']}_{list(x['features'].keys())[0]}") \
        .process(SignalProcessor())

    # Sink to Kafka or database
    stream.add_sink(...)  # Configure output sink

    return env


if __name__ == "__main__":
    env = create_stream_processor()
    env.execute("SecondGradient Stream Processor")