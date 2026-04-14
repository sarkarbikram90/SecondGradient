import json
import os
import sqlite3
import threading
from datetime import datetime

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_DIR = os.getenv('DATA_DIR', os.path.join(ROOT_DIR, 'data'))
DB_PATH = os.getenv('DB_PATH', os.path.join(DATA_DIR, 'secondgradient.db'))

os.makedirs(DATA_DIR, exist_ok=True)
DB_LOCK = threading.Lock()


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn


def format_timestamp(timestamp: float) -> str:
    return datetime.utcfromtimestamp(timestamp).isoformat()


def init_db():
    with DB_LOCK, get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                features JSON NOT NULL,
                prediction REAL
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                feature TEXT NOT NULL,
                drift REAL NOT NULL,
                velocity REAL NOT NULL,
                acceleration REAL NOT NULL,
                timestamp DATETIME NOT NULL
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                risk TEXT NOT NULL,
                time_to_failure REAL,
                confidence TEXT NOT NULL,
                root_cause TEXT NOT NULL,
                timestamp DATETIME NOT NULL
            );
            """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS ix_events_model_timestamp ON events(model, timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_signals_model_timestamp ON signals(model, timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_predictions_model_timestamp ON predictions(model, timestamp);")

        conn.commit()
