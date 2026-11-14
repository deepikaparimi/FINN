import os
import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT_DIR / "backend" / "data" / "finn.sqlite3"


def get_database_path() -> Path:
    configured_path = os.getenv("DATABASE_PATH", "").strip()
    if not configured_path:
        return DEFAULT_DB_PATH
    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def initialize_database() -> None:
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS download_cache (
                cache_key TEXT PRIMARY KEY,
                source_url TEXT NOT NULL,
                content_type TEXT,
                payload BLOB NOT NULL,
                saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_prices (
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                source TEXT NOT NULL,
                PRIMARY KEY (ticker, trade_date)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                volume_multiplier REAL NOT NULL,
                price_change_percent REAL NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS announcements (
                id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                company TEXT NOT NULL,
                time TEXT NOT NULL,
                subject TEXT NOT NULL,
                category TEXT NOT NULL,
                attachment_link TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_data (
                ticker TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                source_mode TEXT NOT NULL,
                saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO alert_rules
                (id, volume_multiplier, price_change_percent)
            VALUES (1, 2.0, 3.0)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_answers (
                request_key TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                model TEXT NOT NULL,
                answer TEXT NOT NULL,
                source_documents TEXT NOT NULL DEFAULT '[]',
                saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def database_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(get_database_path())
    connection.row_factory = sqlite3.Row
    return connection
