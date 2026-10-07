"""water_events repository."""

from __future__ import annotations

import sqlite3

from backend.db.connection import Database

VALID_TYPES = ("reminder_shown", "drank", "snoozed", "dismissed")


class WaterRepo:
    def __init__(self, db: Database):
        self.db = db

    def add(self, timestamp: str, date: str, type: str) -> int:
        if type not in VALID_TYPES:
            raise ValueError(f"invalid water event type: {type}")
        cur = self.db.execute(
            "INSERT INTO water_events(timestamp, date, type) VALUES(?,?,?)",
            (timestamp, date, type),
        )
        return int(cur.lastrowid or 0)

    def count_drunk(self, date: str) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS c FROM water_events WHERE date = ? AND type = 'drank'",
            (date,),
        )
        return int(row["c"])

    def last(self, types: tuple[str, ...] | None = None) -> sqlite3.Row | None:
        """Most recent event, optionally restricted to given types."""
        sql = "SELECT * FROM water_events"
        params: list[object] = []
        if types:
            sql += " WHERE type IN (" + ",".join("?" * len(types)) + ")"
            params.extend(types)
        sql += " ORDER BY id DESC LIMIT 1"
        return self.db.query_one(sql, params)

    def last_of_type(self, type: str) -> sqlite3.Row | None:
        return self.last((type,))

    def events_on(self, date: str) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT * FROM water_events WHERE date = ? ORDER BY id", (date,)
        )
