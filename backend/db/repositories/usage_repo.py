"""usage_sessions repository: writes and aggregate reads for Usage/Stats."""

from __future__ import annotations

import sqlite3

from backend.db.connection import Database


class UsageRepo:
    def __init__(self, db: Database):
        self.db = db

    # ---- write ----

    def insert_session(
        self,
        application: str,
        start_time: str,
        end_time: str,
        duration_seconds: int,
        date: str,
        website: str | None = None,
        window_title: str | None = None,
    ) -> int:
        cur = self.db.execute(
            "INSERT INTO usage_sessions"
            "(application, website, window_title, start_time, end_time,"
            " duration_seconds, date) VALUES(?,?,?,?,?,?,?)",
            (application, website, window_title, start_time, end_time,
             duration_seconds, date),
        )
        return int(cur.lastrowid or 0)

    # ---- read ----

    def sum_seconds(
        self,
        start_date: str,
        end_date: str,
        website: str | None = None,
        application: str | None = None,
    ) -> int:
        sql = ("SELECT COALESCE(SUM(duration_seconds), 0) AS s FROM usage_sessions"
               " WHERE date BETWEEN ? AND ?")
        params: list[object] = [start_date, end_date]
        if website is not None:
            sql += " AND website = ?"
            params.append(website)
        if application is not None:
            sql += " AND application = ?"
            params.append(application)
        return int(self.db.query_one(sql, params)["s"])

    def daily_totals(
        self,
        start_date: str,
        end_date: str,
        website: str | None = None,
    ) -> dict[str, int]:
        """{date: seconds} for every day in [start_date, end_date] (0-filled)."""
        sql = ("SELECT date, SUM(duration_seconds) AS s FROM usage_sessions"
               " WHERE date BETWEEN ? AND ?")
        params: list[object] = [start_date, end_date]
        if website is not None:
            sql += " AND website = ?"
            params.append(website)
        sql += " GROUP BY date"
        rows = {r["date"]: int(r["s"]) for r in self.db.query(sql, params)}
        from datetime import date as _date, timedelta

        d0 = _date.fromisoformat(start_date)
        d1 = _date.fromisoformat(end_date)
        out: dict[str, int] = {}
        cur = d0
        while cur <= d1:
            key = cur.isoformat()
            out[key] = rows.get(key, 0)
            cur += timedelta(days=1)
        return out

    def top_application(self, start_date: str, end_date: str) -> tuple[str, int] | None:
        row = self.db.query_one(
            "SELECT application, SUM(duration_seconds) AS s FROM usage_sessions"
            " WHERE date BETWEEN ? AND ? GROUP BY application"
            " ORDER BY s DESC LIMIT 1",
            (start_date, end_date),
        )
        return (row["application"], int(row["s"])) if row else None

    def longest_session(self, start_date: str, end_date: str) -> sqlite3.Row | None:
        return self.db.query_one(
            "SELECT application, website, duration_seconds, start_time"
            " FROM usage_sessions WHERE date BETWEEN ? AND ?"
            " ORDER BY duration_seconds DESC LIMIT 1",
            (start_date, end_date),
        )

    def most_active_hour(self, start_date: str, end_date: str) -> tuple[int, int] | None:
        """(hour 0-23, seconds) of the busiest start hour."""
        row = self.db.query_one(
            "SELECT CAST(substr(start_time, 12, 2) AS INTEGER) AS hour,"
            " SUM(duration_seconds) AS s FROM usage_sessions"
            " WHERE date BETWEEN ? AND ? GROUP BY hour ORDER BY s DESC, hour ASC LIMIT 1",
            (start_date, end_date),
        )
        return (int(row["hour"]), int(row["s"])) if row else None

    def site_breakdown(self, start_date: str, end_date: str, limit: int = 5) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT website, SUM(duration_seconds) AS s FROM usage_sessions"
            " WHERE date BETWEEN ? AND ? AND website IS NOT NULL"
            " GROUP BY website ORDER BY s DESC LIMIT ?",
            (start_date, end_date, limit),
        )

    def top_applications(self, start_date: str, end_date: str, limit: int = 10) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT application, SUM(duration_seconds) AS s FROM usage_sessions"
            " WHERE date BETWEEN ? AND ?"
            " GROUP BY application ORDER BY s DESC LIMIT ?",
            (start_date, end_date, limit),
        )
