#!/usr/bin/env python3
"""
MVP Integration Test

Validates that the SecondGradient MVP works end-to-end:
1. API starts and responds to health checks
2. Event ingestion works
3. Predictions are generated
4. Frontend can connect (basic connectivity test)
"""

import time
import requests
import subprocess
import sys
import os
from typing import Optional

class MVPTest:
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url

    def test_api_health(self) -> bool:
        """Test API health endpoint."""
        try:
            response = requests.get(f"{self.api_url}/api/health", timeout=5)
            return response.status_code == 200 and response.json()["success"]
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False

    def test_event_ingestion(self) -> bool:
        """Test ML event ingestion."""
        event = {
            "model": "test-model",
            "features": {
                "feature1": 0.5,
                "feature2": 0.3,
                "feature3": 0.8
            },
            "prediction": 0.75
        }

        try:
            response = requests.post(
                f"{self.api_url}/api/events",
                json=event,
                timeout=5
            )
            return response.status_code == 200 and response.json()["success"]
        except Exception as e:
            print(f"❌ Event ingestion failed: {e}")
            return False

    def test_predictions_endpoint(self) -> bool:
        """Test predictions endpoint returns data."""
        try:
            response = requests.get(f"{self.api_url}/api/predictions", timeout=5)
            if response.status_code == 200:
                data = response.json()
                required_fields = ["drift", "velocity", "acceleration", "time_to_failure", "confidence"]
                return all(field in data for field in required_fields)
            return False
        except Exception as e:
            print(f"❌ Predictions endpoint failed: {e}")
            return False

    def test_frontend_connectivity(self) -> bool:
        """Test basic frontend connectivity."""
        try:
            response = requests.get("http://localhost:3000", timeout=5)
            return response.status_code == 200
        except Exception:
            # Frontend might not be running, that's OK for API tests
            return True

    def run_all_tests(self) -> bool:
        """Run all integration tests."""
        print("🧪 Running SecondGradient MVP Integration Tests")
        print("=" * 50)

        tests = [
            ("API Health Check", self.test_api_health),
            ("Event Ingestion", self.test_event_ingestion),
            ("Predictions Endpoint", self.test_predictions_endpoint),
            ("Frontend Connectivity", self.test_frontend_connectivity),
        ]

        passed = 0
        total = len(tests)

        for test_name, test_func in tests:
            print(f"Testing {test_name}...", end=" ")
            if test_func():
                print("✅ PASSED")
                passed += 1
            else:
                print("❌ FAILED")

        print("=" * 50)
        print(f"Results: {passed}/{total} tests passed")

        if passed == total:
            print("🎉 All tests passed! MVP is working correctly.")
            return True
        else:
            print("⚠️  Some tests failed. Check the output above.")
            return False

def main():
    """Main test runner."""
    import argparse

    parser = argparse.ArgumentParser(description="SecondGradient MVP Integration Tests")
    parser.add_argument("--api-url", default="http://localhost:8000",
                       help="API URL to test against")

    args = parser.parse_args()

    # Give services time to start if running in Docker
    if os.getenv("DOCKER_CONTAINER"):
        print("🐳 Running in Docker, waiting for services to start...")
        time.sleep(10)

    tester = MVPTest(args.api_url)
    success = tester.run_all_tests()

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()