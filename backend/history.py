"""SQLite-backed history store. DB lives next to this file as history.db."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "history.db"
MAX_PER_TAB = 50


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tab         TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                title       TEXT    NOT NULL,
                thumbnail   TEXT,
                image       TEXT,
                data        TEXT    NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tab_time ON history(tab, id DESC)"
        )
        # Migration: add image column if missing (older DBs)
        try:
            conn.execute("ALTER TABLE history ADD COLUMN image TEXT")
        except Exception:
            pass


def add_entry(
    tab: str,
    title: str,
    data: dict,
    thumbnail: str | None = None,
    image: str | None = None,
) -> int:
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO history (tab, created_at, title, thumbnail, image, data) VALUES (?,?,?,?,?,?)",
            (tab, created_at, title, thumbnail, image, json.dumps(data)),
        )
        entry_id = cursor.lastrowid
        # Trim to MAX_PER_TAB oldest entries
        conn.execute(
            """DELETE FROM history WHERE tab = ? AND id NOT IN (
                   SELECT id FROM history WHERE tab = ? ORDER BY id DESC LIMIT ?
               )""",
            (tab, tab, MAX_PER_TAB),
        )
    return entry_id


def get_entries(tab: str, limit: int = MAX_PER_TAB) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, tab, created_at, title, thumbnail, image, data "
            "FROM history WHERE tab = ? ORDER BY id DESC LIMIT ?",
            (tab, limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def delete_entry(entry_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM history WHERE id = ?", (entry_id,))
    return cur.rowcount > 0


def clear_tab(tab: str) -> int:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM history WHERE tab = ?", (tab,))
    return cur.rowcount


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["data"] = json.loads(d["data"])
    return d
