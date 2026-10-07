"""SQLite connection + a small thread-safe Database wrapper.

- row_factory = sqlite3.Row
- WAL journal (file DBs), foreign keys on, busy timeout
- Database.execute/query commit per call (autocommit), transaction() for groups
- meta helpers (schema_version, heartbeat, ...)
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


class Database:
    """One connection guarded by a lock. Fine for a desktop companion."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self._conn = connect(path)
        self._lock = threading.RLock()

    @property
    def raw(self) -> sqlite3.Connection:
        return self._conn

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
        return cur

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, tuple(params)).fetchall())

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def get_meta(db: Database, key: str, default: str | None = None) -> str | None:
    row = db.query_one("SELECT value FROM meta WHERE key = ?", (key,))
    return row["value"] if row else default


def set_meta(db: Database, key: str, value: str) -> None:
    db.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
