"""
SecondGradient API - MVP Version

FastAPI backend for ingesting ML events and serving predictions.
"""

import json
import logging
import os
import sys
import time
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from services.api.db import DB_PATH, get_connection, init_db
from services.api.repository import (
    save_event,
    get_events,
    save_signal,
    get_signals,
    save_prediction,
    get_latest_prediction,
)
from services.processor.engine import engine

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('secondgradient')

app = FastAPI(
    title='SecondGradient API',
    description='Predictive Intelligence for ML Systems',
    version='0.1.0',
)

metrics = {
    'events_processed': 0,
    'signals_computed': 0,
    'predictions_generated': 0,
    'latency_seconds': [],
}

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000', 'http://127.0.0.1:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
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


@app.on_event('startup')
async def startup_event():
    init_db()
    logger.info('Database initialized and ready')


def classify_root_cause(prediction: Dict[str, Any]) -> str:
    if prediction.get('avg_acceleration', 0) > 0.002:
        return 'DATA'
    if prediction.get('avg_velocity', 0) > 0.02:
        return 'MODEL'
    if prediction.get('avg_drift', 0) > 0.25:
        return 'DATA'
    return 'EARLY_WARNING'


@app.post('/api/events', response_model=APIResponse)
async def ingest_event(event: MLEvent):
    start_time = time.time()
    logger.info('Event received model=%s', event.model)

    try:
        event_timestamp = event.timestamp or time.time()
        event_id = save_event(event.model, event_timestamp, event.features, event.prediction)
        logger.info('Event ingested model=%s event_id=%s', event.model, event_id)

        result = engine.process_event(model=event.model, features=event.features, timestamp=event_timestamp)
        logger.info('Event processed model=%s', event.model)

        for feature_name, feature_result in result.get('features', {}).items():
            save_signal(
                model=event.model,
                feature=feature_name,
                drift=feature_result['drift'],
                velocity=feature_result['velocity'],
                acceleration=feature_result['acceleration'],
                timestamp=event_timestamp,
            )
            metrics['signals_computed'] += 1
            logger.info(
                'Signal computed model=%s feature=%s drift=%.4f velocity=%.6f acceleration=%.6f',
                event.model,
                feature_name,
                feature_result['drift'],
                feature_result['velocity'],
                feature_result['acceleration'],
            )

        prediction = result.get('prediction', {})
        root_cause = classify_root_cause(prediction)
        prediction_id = save_prediction(
            model=event.model,
            risk=prediction.get('risk', 'UNKNOWN'),
            time_to_failure=prediction.get('time_to_failure_minutes'),
            confidence=prediction.get('confidence', 'LOW'),
            root_cause=root_cause,
            timestamp=event_timestamp,
        )
        metrics['predictions_generated'] += 1
        logger.info(
            'Prediction generated model=%s id=%s risk=%s ttf=%s confidence=%s root_cause=%s',
            event.model,
            prediction_id,
            prediction.get('risk'),
            prediction.get('time_to_failure_minutes'),
            prediction.get('confidence'),
            root_cause,
        )

        metrics['events_processed'] += 1
        latency = time.time() - start_time
        metrics['latency_seconds'].append(latency)

        return APIResponse(
            success=True,
            data={'event_id': event_id, 'prediction_id': prediction_id, 'result': result},
            message='Event processed successfully',
            timestamp=time.time(),
        )

    except Exception as e:
        logger.exception('Failed to ingest event model=%s', event.model)
        raise HTTPException(status_code=500, detail=f'Processing failed: {str(e)}')


@app.get('/api/predictions')
async def get_predictions(model: Optional[str] = Query(None)):
    try:
        prediction = get_latest_prediction(model)
        if prediction:
            return prediction

        return {
            'model': model or 'unknown',
            'risk': 'LOW',
            'time_to_failure': None,
            'confidence': 'LOW',
            'root_cause': 'NONE',
            'timestamp': time.time(),
        }
    except Exception as e:
        logger.exception('Failed to fetch latest prediction')
        raise HTTPException(status_code=500, detail=f'Failed to get predictions: {str(e)}')


@app.get('/api/signals')
async def get_signal_history(model: Optional[str] = Query(None), limit: int = 100):
    try:
        signals = get_signals(model, limit)
        return {'count': len(signals), 'signals': signals}
    except Exception as e:
        logger.exception('Failed to fetch signals')
        raise HTTPException(status_code=500, detail=f'Failed to get signals: {str(e)}')


@app.get('/api/metrics')
async def get_metrics():
    average_latency = None
    if metrics['latency_seconds']:
        average_latency = sum(metrics['latency_seconds']) / len(metrics['latency_seconds'])

    return {
        'events_processed': metrics['events_processed'],
        'signals_computed': metrics['signals_computed'],
        'predictions_generated': metrics['predictions_generated'],
        'average_latency_seconds': average_latency,
    }


@app.get('/api/health', response_model=APIResponse)
async def health_check():
    try:
        with get_connection() as conn:
            conn.execute('SELECT 1').fetchone()

        return APIResponse(
            success=True,
            data={'status': 'healthy', 'engine_initialized': True, 'db_path': DB_PATH},
            message='Service is healthy',
            timestamp=time.time(),
        )

    except Exception as e:
        logger.exception('Health check failed')
        raise HTTPException(status_code=503, detail='Service unhealthy')


@app.get('/api/models')
async def list_models():
    try:
        events = get_events(limit=1000)
        models = sorted({event['model'] for event in events})
        return {'models': models, 'count': len(models)}
    except Exception as e:
        logger.exception('Failed to list models')
        raise HTTPException(status_code=500, detail=f'Failed to list models: {str(e)}')


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)