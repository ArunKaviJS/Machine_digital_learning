"""UsageService: answers built from usage_sessions (numbers only, no text)."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from backend.db.connection import Database
from backend.db.repositories.usage_repo import UsageRepo
from backend.services.periods import period_to_range


class UsageService:
    def __init__(self, db: Database, today_fn: Callable[[], date] = date.today):
        self.repo = UsageRepo(db)
        self.today_fn = today_fn

    def _range(self, period: str) -> tuple[str, str]:
        return period_to_range(period, self.today_fn())

    def usage(self, period: str = "today", site: str | None = None,
              app: str | None = None) -> dict[str, Any]:
        start, end = self._range(period)
        seconds = self.repo.sum_seconds(start, end, website=site, application=app)
        return {"period": period, "site": site, "app": app,
                "start": start, "end": end, "seconds": seconds}

    def screen_time(self, period: str = "today") -> dict[str, Any]:
        start, end = self._range(period)
        return {"period": period, "start": start, "end": end,
                "seconds": self.repo.sum_seconds(start, end)}

    def top_app(self, period: str = "today") -> dict[str, Any] | None:
        start, end = self._range(period)
        row = self.repo.top_application(start, end)
        if not row:
            return None
        return {"period": period, "application": row[0], "seconds": row[1]}

    def longest_session(self, period: str = "today") -> dict[str, Any] | None:
        start, end = self._range(period)
        row = self.repo.longest_session(start, end)
        if not row:
            return None
        return {"period": period, "application": row["application"],
                "website": row["website"], "seconds": row["duration_seconds"],
                "start_time": row["start_time"]}

    def most_active_hour(self, period: str = "today") -> dict[str, Any] | None:
        start, end = self._range(period)
        row = self.repo.most_active_hour(start, end)
        if not row:
            return None
        return {"period": period, "hour": row[0], "seconds": row[1]}

    def summary(self, period: str = "today") -> dict[str, Any]:
        start, end = self._range(period)
        total_seconds = self.repo.sum_seconds(start, end)
        sites_rows = self.repo.site_breakdown(start, end, limit=10)
        sites = [{"site": r["website"], "seconds": int(r["s"])} for r in sites_rows]
        apps_rows = self.repo.top_applications(start, end, limit=10)
        apps = [{"application": r["application"], "seconds": int(r["s"])} for r in apps_rows]
        return {
            "period": period,
            "start": start,
            "end": end,
            "total_seconds": total_seconds,
            "sites": sites,
            "apps": apps,
        }
