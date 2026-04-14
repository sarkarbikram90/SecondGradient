import os
import signal
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest
import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
API_DIR = ROOT_DIR / 'services' / 'api'
DB_PATH = ROOT_DIR / 'data' / 'secondgradient.db'

API_URL = 'http://127.0.0.1:8000'


def start_api_process(port: int = 8000):
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT_DIR)
    env['DB_PATH'] = str(DB_PATH)
    env['DATA_DIR'] = str(ROOT_DIR / 'data')

    process = subprocess.Popen(
        ['python', '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(port)],
        cwd=str(API_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            response = requests.get(f'http://127.0.0.1:{port}/api/health', timeout=2)
            if response.status_code == 200:
                return process
        except requests.RequestException:
            time.sleep(0.5)

    process.kill()
    raise RuntimeError('API did not start in time')


def stop_api_process(process: subprocess.Popen):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture(scope='module')
def api_server():
    process = start_api_process()
    yield process
    stop_api_process(process)


def open_db():
    assert DB_PATH.exists(), 'Database file not found'
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def test_system_health(api_server):
    response = requests.get(f'{API_URL}/api/health', timeout=5)
    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    assert body['data']['status'] == 'healthy'

    with open_db() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row['name'] for row in cursor.fetchall()}
    assert {'events', 'signals', 'predictions'} <= tables


def test_event_ingestion(api_server):
    payload = {
        'model': 'test-model',
        'features': {'feature1': 0.5, 'feature2': 0.3, 'feature3': 0.8},
        'prediction': 0.75,
    }
    response = requests.post(f'{API_URL}/api/events', json=payload, timeout=5)
    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    assert 'event_id' in body['data']
    assert 'prediction_id' in body['data']

    with open_db() as conn:
        cursor = conn.execute('SELECT model, prediction FROM events ORDER BY id DESC LIMIT 1')
        event = cursor.fetchone()
    assert event is not None
    assert event['model'] == 'test-model'
    assert event['prediction'] == 0.75


def test_signal_generation(api_server):
    model = 'signal-test-model'
    for value in [0.1, 0.2, 0.25, 0.3, 0.45, 0.6]:
        payload = {'model': model, 'features': {'x': value, 'y': value + 0.05}, 'prediction': 0.5}
        response = requests.post(f'{API_URL}/api/events', json=payload, timeout=5)
        assert response.status_code == 200

    with open_db() as conn:
        cursor = conn.execute(
            'SELECT drift, velocity, acceleration FROM signals WHERE model = ? ORDER BY id DESC LIMIT 5',
            (model,),
        )
        rows = cursor.fetchall()
    assert len(rows) >= 3
    assert any(row['drift'] > 0 for row in rows)
    assert any(row['velocity'] != 0 for row in rows)
    assert any(row['acceleration'] != 0 for row in rows)


def test_prediction_validation(api_server):
    model = 'pred-test-model'
    for step in range(8):
        value = 0.2 + step * 0.1
        payload = {'model': model, 'features': {'a': value, 'b': value * 1.1}, 'prediction': 0.6}
        response = requests.post(f'{API_URL}/api/events', json=payload, timeout=5)
        assert response.status_code == 200

    response = requests.get(f'{API_URL}/api/predictions', params={'model': model}, timeout=5)
    assert response.status_code == 200
    body = response.json()
    assert body['model'] == model
    assert body['risk'] in {'MEDIUM', 'HIGH', 'CRITICAL', 'UNKNOWN'}
    assert 'time_to_failure' in body
    assert 'confidence' in body


def test_failure_scenario(api_server):
    model = 'failure-sim-model'
    for step in range(12):
        value = 0.1 + (step ** 2) * 0.01
        payload = {'model': model, 'features': {'f1': value, 'f2': value + 0.02}, 'prediction': 0.4}
        response = requests.post(f'{API_URL}/api/events', json=payload, timeout=5)
        assert response.status_code == 200

    response = requests.get(f'{API_URL}/api/predictions', params={'model': model}, timeout=5)
    body = response.json()
    assert body['risk'] in {'HIGH', 'CRITICAL'}
    assert body['time_to_failure'] is not None

    with open_db() as conn:
        cursor = conn.execute('SELECT acceleration FROM signals WHERE model = ? ORDER BY id DESC LIMIT 5', (model,))
        accelerations = [row['acceleration'] for row in cursor.fetchall()]
    assert any(acc > 0 for acc in accelerations)


def test_data_persistence_across_restart():
    restart_port = 8001
    model = 'persistence-test-model'
    payload = {'model': model, 'features': {'x': 0.7, 'y': 0.8}, 'prediction': 0.9}

    api_process = start_api_process(port=restart_port)
    try:
        response = requests.post(f'http://127.0.0.1:{restart_port}/api/events', json=payload, timeout=5)
        assert response.status_code == 200

        with open_db() as conn:
            cursor = conn.execute('SELECT COUNT(*) AS count FROM predictions WHERE model = ?', (model,))
            initial_count = cursor.fetchone()['count']
    finally:
        stop_api_process(api_process)

    time.sleep(1)
    api_process = start_api_process(port=restart_port)
    try:
        with open_db() as conn:
            cursor = conn.execute('SELECT COUNT(*) AS count FROM predictions WHERE model = ?', (model,))
            restarted_count = cursor.fetchone()['count']
        assert restarted_count == initial_count
    finally:
        stop_api_process(api_process)
