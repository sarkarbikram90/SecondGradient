"""
SecondGradient API - MVP Version

FastAPI backend for ingesting ML events and serving predictions.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import time
import uvicorn

from services.processor.engine import engine

app = FastAPI(
    title="SecondGradient API",
    description="Predictive Intelligence for ML Systems",
    version="0.1.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MLEvent(BaseModel):
    """ML inference event payload."""
    model: str
    timestamp: Optional[float] = None
    features: Dict[str, float]
    prediction: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class APIResponse(BaseModel):
    """Standard API response."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    timestamp: float


@app.post("/api/events", response_model=APIResponse)
async def ingest_event(event: MLEvent):
    """
    Ingest an ML inference event for processing.

    This endpoint accepts ML prediction events and processes them through
    the signal engine to detect drift, velocity, and acceleration patterns.
    """
    try:
        # Process the event
        result = engine.process_event(
            model=event.model,
            features=event.features,
            timestamp=event.timestamp
        )

        return APIResponse(
            success=True,
            data=result,
            message="Event processed successfully",
            timestamp=time.time()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.get("/api/models/{model_id}", response_model=APIResponse)
async def get_model_state(model_id: str):
    """
    Get current state and predictions for a model.

    Returns the latest signal analysis including drift, velocity,
    acceleration, and failure predictions.
    """
    try:
        state = engine.get_model_state(model_id)

        # Add prediction if we have enough data
        if state["feature_count"] > 0:
            # Get the latest prediction by processing a dummy event
            # In production, this would be cached
            prediction_result = engine.process_event(model_id, {}, time.time())
            if "prediction" in prediction_result:
                state["prediction"] = prediction_result["prediction"]

        return APIResponse(
            success=True,
            data=state,
            message=f"Retrieved state for model {model_id}",
            timestamp=time.time()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get model state: {str(e)}")


@app.get("/api/health", response_model=APIResponse)
async def health_check():
    """Health check endpoint."""
    return APIResponse(
        success=True,
        data={"status": "healthy", "engine_initialized": True},
        message="Service is healthy",
        timestamp=time.time()
    )


@app.get("/api/models", response_model=APIResponse)
async def list_models():
    """List all models being tracked."""
    try:
        models = set()
        for key in engine.states.keys():
            model = key.split(":", 1)[0]
            models.add(model)

        return APIResponse(
            success=True,
            data={"models": list(models), "count": len(models)},
            message=f"Found {len(models)} models",
            timestamp=time.time()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list models: {str(e)}")


@app.get("/api/predictions")
async def get_latest_predictions():
    """
    Get the latest predictions for all models.

    Returns real-time drift analysis data for frontend visualization.
    """
    try:
        predictions = []

        for model_key, state in engine.states.items():
            if state["feature_count"] > 0:
                # Get the latest data point
                latest_data = state["data"][-1] if state["data"] else None
                if latest_data:
                    predictions.append({
                        "model": model_key.split(":", 1)[0],
                        "timestamp": latest_data["timestamp"],
                        "drift": latest_data["drift"],
                        "velocity": latest_data["velocity"],
                        "acceleration": latest_data["acceleration"],
                        "time_to_failure": latest_data["time_to_failure"],
                        "confidence": latest_data["confidence"]
                    })

        # Return the most recent prediction across all models
        if predictions:
            latest = max(predictions, key=lambda x: x["timestamp"])
            return latest
        else:
            # Return default values if no data yet
            return {
                "model": "unknown",
                "timestamp": time.time(),
                "drift": 0.0,
                "velocity": 0.0,
                "acceleration": 0.0,
                "time_to_failure": 3600.0,  # 1 hour default
                "confidence": 0.0
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get predictions: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )