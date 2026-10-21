"""Versioned migrations. Applied in order, recorded in meta.schema_version.

To add a migration: append (version, name, sql) to MIGRATIONS. Never edit an
old one. migrate() is idempotent.
"""

from __future__ import annotations

import logging
import sqlite3

from backend.db.connection import SCHEMA_PATH

logger = logging.getLogger("arun.db")

CHAT_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id              TEXT PRIMARY KEY,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    request         TEXT NOT NULL DEFAULT '',
    awaiting_answer INTEGER NOT NULL DEFAULT 0,
    user_texts      TEXT NOT NULL DEFAULT '[]',
    active_window   TEXT
);
CREATE TABLE IF NOT EXISTS chat_messages (
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    seq        INTEGER NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
"""

MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "initial schema", SCHEMA_PATH.read_text(encoding="utf-8")),
    (2, "chat context memory", CHAT_SCHEMA),
]


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    return int(row[0]) if row else 0


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations; return the resulting schema version."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    version = current_version(conn)
    for target, name, sql in sorted(MIGRATIONS):
        if target <= version:
            continue
        # schema.sql uses IF NOT EXISTS, so a partial run is safe to retry
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(target),),
        )
        version = target
        logger.info("applied migration %s: %s", target, name)
    return version
