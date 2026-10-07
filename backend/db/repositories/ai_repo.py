"""ai_calls repository: latency/success log for tuning (prompt only if enabled)."""

from __future__ import annotations

import sqlite3

from backend.db.connection import Database


class AiRepo:
    def __init__(self, db: Database):
        self.db = db

    def log_call(
        self,
        timestamp: str,
        intent: str | None,
        latency_ms: int,
        success: bool,
        prompt: str | None = None,
    ) -> int:
        cur = self.db.execute(
            "INSERT INTO ai_calls(timestamp, intent, latency_ms, success, prompt)"
            " VALUES(?,?,?,?,?)",
            (timestamp, intent, latency_ms, 1 if success else 0, prompt),
        )
        return int(cur.lastrowid or 0)

    def recent(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT id, timestamp, intent, latency_ms, success FROM ai_calls"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        )

    def stats(self) -> dict:
        row = self.db.query_one(
            "SELECT COUNT(*) AS n, COALESCE(AVG(latency_ms),0) AS avg_ms,"
            " COALESCE(SUM(success),0) AS ok FROM ai_calls"
        )
        return {"calls": int(row["n"]), "avg_ms": int(row["avg_ms"]),
                "successes": int(row["ok"])}
