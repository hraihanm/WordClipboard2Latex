"""SQLite-backed settings store. Uses history.db alongside history table."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "history.db"

DEFAULTS = {
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "llava",
    "gemini_api_key": "",  # optional override; .env GEMINI_API_KEY takes precedence
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_settings_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    for key, val in DEFAULTS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(val) if isinstance(val, (dict, list)) else str(val)),
        )


def init_settings() -> None:
    """Ensure settings table exists. Call at app startup."""
    with _connect() as conn:
        _ensure_settings_table(conn)


def get_all() -> dict:
    """Return all settings as a flat dict."""
    with _connect() as conn:
        _ensure_settings_table(conn)
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    result = dict(DEFAULTS)
    for row in rows:
        key, val = row["key"], row["value"]
        try:
            result[key] = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            result[key] = val
    return result


def get(key: str) -> str | None:
    """Get a single setting value."""
    return get_all().get(key)


def set_many(updates: dict) -> None:
    """Update multiple settings."""
    with _connect() as conn:
        _ensure_settings_table(conn)
        for key, val in updates.items():
            if key not in DEFAULTS:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(val) if isinstance(val, (dict, list)) else str(val)),
            )
