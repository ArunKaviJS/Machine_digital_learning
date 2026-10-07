"""guard_events repository + persisted streak bookkeeping in meta."""

from __future__ import annotations

import sqlite3

from backend.db.connection import Database, get_meta, set_meta

VALID_TYPES = ("nag", "countdown_start", "tab_closed", "cancelled", "snoozed")

STREAK_KEY = "guard.streak_seconds"
STREAK_RESET_KEY = "guard.streak_since"


class GuardRepo:
    def __init__(self, db: Database):
        self.db = db

    def add_event(self, timestamp: str, date: str, type: str, site: str | None = None) -> int:
        if type not in VALID_TYPES:
            raise ValueError(f"invalid guard event type: {type}")
        cur = self.db.execute(
            "INSERT INTO guard_events(timestamp, date, site, type) VALUES(?,?,?,?)",
            (timestamp, date, site, type),
        )
        return int(cur.lastrowid or 0)

    def recent(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT * FROM guard_events ORDER BY id DESC LIMIT ?", (limit,)
        )

    def events_on(self, date: str) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT * FROM guard_events WHERE date = ? ORDER BY id", (date,)
        )

    # streak survives restarts (meta table)
    def get_streak(self) -> int:
        return int(get_meta(self.db, STREAK_KEY, "0") or 0)

    def set_streak(self, seconds: int, since: str) -> None:
        set_meta(self.db, STREAK_KEY, str(max(0, seconds)))
        set_meta(self.db, STREAK_RESET_KEY, since)

    def get_streak_since(self) -> str | None:
        return get_meta(self.db, STREAK_RESET_KEY)
