#!/usr/bin/env python3
"""
SecondGradient Data Simulator

Generates synthetic ML inference events with controlled drift patterns
to demonstrate the predictive capabilities of SecondGradient.
"""

import time
import random
import requests
import json
from typing import Dict, List, Any
import numpy as np


class DriftSimulator:
    """Simulates ML inference data with realistic drift patterns."""

    def __init__(self, api_url: str = "http://api:8000", seed: int | None = None):
        self.api_url = api_url
        self.models = ["rec-v1", "fraud-detector", "pricing-model"]
        self.seed = seed
        if self.seed is not None:
            random.seed(self.seed)
            np.random.seed(self.seed)

        # Baseline feature distributions
        self.baselines = {
            "rec-v1": {
                "user_age": {"mean": 35, "std": 12},
                "item_category": {"mean": 0.5, "std": 0.3},  # Normalized
                "session_length": {"mean": 120, "std": 60}
            },
            "fraud-detector": {
                "transaction_amount": {"mean": 100, "std": 50},
                "user_history_score": {"mean": 0.7, "std": 0.2},
                "device_fingerprint": {"mean": 0.5, "std": 0.3}
            },
            "pricing-model": {
                "demand_score": {"mean": 0.6, "std": 0.25},
                "competitor_price": {"mean": 50, "std": 15},
                "seasonal_factor": {"mean": 0.5, "std": 0.2}
            }
        }

    def generate_normal_event(self, model: str) -> Dict[str, Any]:
        """Generate a normal inference event."""
        features = {}
        baseline = self.baselines[model]

        for feature, params in baseline.items():
            # Add some natural variation
            value = np.random.normal(params["mean"], params["std"] * 0.1)
            # Clamp to reasonable ranges
            if "category" in feature or "score" in feature or "factor" in feature:
                value = np.clip(value, 0, 1)
            features[feature] = round(float(value), 3)

        return {
            "model": model,
            "timestamp": time.time(),
            "features": features,
            "prediction": round(random.uniform(0.1, 0.9), 3),
            "metadata": {"source": "simulator", "normal": True}
        }

    def generate_drift_event(self, model: str, drift_factor: float = 0.1) -> Dict[str, Any]:
        """Generate an event with gradual drift."""
        features = {}
        baseline = self.baselines[model]

        for feature, params in baseline.items():
            # Introduce gradual drift
            drift_amount = params["std"] * drift_factor
            new_mean = params["mean"] + drift_amount

            value = np.random.normal(new_mean, params["std"] * 0.15)
            # Clamp to reasonable ranges
            if "category" in feature or "score" in feature or "factor" in feature:
                value = np.clip(value, 0, 1)
            features[feature] = round(float(value), 3)

        return {
            "model": model,
            "timestamp": time.time(),
            "features": features,
            "prediction": round(random.uniform(0.1, 0.9), 3),
            "metadata": {"source": "simulator", "drift_factor": drift_factor}
        }

    def generate_accelerating_drift(self, model: str, step: int, max_steps: int = 100) -> Dict[str, Any]:
        """Generate accelerating drift that will trigger predictions."""
        progress = step / max_steps  # 0 to 1
        drift_factor = progress * 0.5  # Gradually increase drift

        features = {}
        baseline = self.baselines[model]

        for feature, params in baseline.items():
            # Accelerating drift: quadratic increase
            drift_amount = params["std"] * drift_factor * (1 + progress)
            new_mean = params["mean"] + drift_amount

            value = np.random.normal(new_mean, params["std"] * 0.2)
            # Clamp to reasonable ranges
            if "category" in feature or "score" in feature or "factor" in feature:
                value = np.clip(value, 0, 1)
            features[feature] = round(float(value), 3)

        return {
            "model": model,
            "timestamp": time.time(),
            "features": features,
            "prediction": round(random.uniform(0.1, 0.9), 3),
            "metadata": {"source": "simulator", "accelerating_drift": True, "step": step}
        }

    def send_event(self, event: Dict[str, Any]) -> bool:
        """Send event to SecondGradient API."""
        try:
            response = requests.post(
                f"{self.api_url}/api/events",
                json=event,
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send event: {e}")
            return False

    def run_normal_simulation(self, duration_seconds: int = 60, events_per_second: int = 2):
        """Run a normal operation simulation."""
        print("🚀 Starting normal operation simulation...")
        print(f"Duration: {duration_seconds}s, Events/sec: {events_per_second}")

        start_time = time.time()
        event_count = 0

        while time.time() - start_time < duration_seconds:
            model = random.choice(self.models)
            event = self.generate_normal_event(model)

            if self.send_event(event):
                event_count += 1
                if event_count % 20 == 0:
                    print(f"📊 Sent {event_count} normal events...")

            time.sleep(1.0 / events_per_second)

        print(f"✅ Normal simulation complete. Sent {event_count} events.")

    def run_drift_simulation(self, duration_seconds: int = 120, events_per_second: int = 2):
        """Run a gradual drift simulation."""
        print("⚠️  Starting gradual drift simulation...")
        print(f"Duration: {duration_seconds}s, Events/sec: {events_per_second}")

        start_time = time.time()
        event_count = 0

        while time.time() - start_time < duration_seconds:
            model = random.choice(self.models)
            # Gradually increase drift over time
            elapsed = time.time() - start_time
            drift_factor = min(elapsed / duration_seconds, 0.3)

            event = self.generate_drift_event(model, drift_factor)

            if self.send_event(event):
                event_count += 1
                if event_count % 20 == 0:
                    print(f"📊 Sent {event_count} drift events (factor: {drift_factor:.2f})...")

            time.sleep(1.0 / events_per_second)

        print(f"✅ Drift simulation complete. Sent {event_count} events.")

    def run_accelerating_failure_simulation(self, model: str = "rec-v1", max_steps: int = 100):
        """Run an accelerating drift simulation that should trigger failure prediction."""
        print(f"🚨 Starting accelerating failure simulation for {model}...")
        print("This will gradually increase drift until failure is predicted.")

        for step in range(max_steps):
            event = self.generate_accelerating_drift(model, step, max_steps)

            if self.send_event(event):
                print(f"📊 Step {step+1}/{max_steps}: Sent accelerating drift event")

                # Check prediction every 10 steps
                if (step + 1) % 10 == 0:
                    try:
                        response = requests.get(f"{self.api_url}/api/models/{model}")
                        if response.status_code == 200:
                            data = response.json()
                            if "data" in data and "prediction" in data["data"]:
                                pred = data["data"]["prediction"]
                                risk = pred.get("risk", "UNKNOWN")
                                ttf = pred.get("time_to_failure_minutes")
                                print(f"   🎯 Current prediction: Risk={risk}, TTF={ttf}min")

                                if risk in ["HIGH", "CRITICAL"] and ttf and ttf < 60:
                                    print(f"   🚨 FAILURE PREDICTED: {ttf} minutes remaining!")
                                    break
                    except Exception as e:
                        print(f"   Error checking prediction: {e}")

            time.sleep(0.5)  # Slow down for visibility

        print("✅ Accelerating failure simulation complete.")


def main():
    """Main simulator entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="SecondGradient Data Simulator")
    parser.add_argument("--api-url", default="http://localhost:8000",
                       help="SecondGradient API URL")
    parser.add_argument("--mode", choices=["normal", "drift", "failure"],
                       default="normal", help="Simulation mode")
    parser.add_argument("--duration", type=int, default=60,
                       help="Simulation duration in seconds")
    parser.add_argument("--model", default="rec-v1",
                       help="Model to use for failure simulation")
    parser.add_argument("--seed", type=int, default=None,
                       help="Optional deterministic seed for reproducible output")

    args = parser.parse_args()

    simulator = DriftSimulator(args.api_url, seed=args.seed)

    if args.mode == "normal":
        simulator.run_normal_simulation(args.duration)
    elif args.mode == "drift":
        simulator.run_drift_simulation(args.duration)
    elif args.mode == "failure":
        simulator.run_accelerating_failure_simulation(args.model)


if __name__ == "__main__":
    main()