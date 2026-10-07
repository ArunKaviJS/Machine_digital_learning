"""StatsService: comparisons and averages (numbers only, no text)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from backend.db.connection import Database
from backend.db.repositories.usage_repo import UsageRepo
from backend.services.periods import days_in_range, period_to_range, shift_days

VALID_COMPARISONS = ("none", "average", "yesterday", "last_week")


class StatsService:
    def __init__(self, db: Database, today_fn: Callable[[], date] = date.today):
        self.repo = UsageRepo(db)
        self.today_fn = today_fn

    def compare_days(self, day_a: str, day_b: str,
                     website: str | None = None,
                     app: str | None = None) -> dict[str, Any]:
        """a vs b (both ISO dates, single days). diff = a - b."""
        a = self.repo.sum_seconds(day_a, day_a, website=website, application=app)
        b = self.repo.sum_seconds(day_b, day_b, website=website, application=app)
        return {"a": day_a, "b": day_b, "a_seconds": a, "b_seconds": b,
                "diff": a - b, "more": a > b, "equal": a == b}

    def average_daily(self, website: str | None = None, app: str | None = None,
                      days: int = 7) -> float:
        """Mean seconds/day over the last `days` days, **excluding today**."""
        today = self.today_fn()
        end = today - timedelta(days=1)
        start = end - timedelta(days=days - 1)
        total = 0
        for i in range(days):
            d = (start + timedelta(days=i)).isoformat()
            total += self.repo.sum_seconds(d, d, website=website, application=app)
        return total / days

    def compare_usage(self, period: str, website: str | None = None,
                      app: str | None = None, comparison: str = "none") -> dict[str, Any]:
        """usage(period) vs a baseline (average / same window shifted / none)."""
        if comparison not in VALID_COMPARISONS:
            raise ValueError(f"unknown comparison: {comparison!r}")
        start, end = self._range(period)
        seconds = self.repo.sum_seconds(start, end, website=website, application=app)
        result: dict[str, Any] = {
            "period": period, "site": website, "app": app,
            "start": start, "end": end, "seconds": seconds,
            "comparison": comparison, "baseline": None, "diff": None,
        }
        if comparison == "none":
            return result
        if comparison == "average":
            days = days_in_range(start, end)
            baseline = self.average_daily(website, app) * days
        elif comparison == "yesterday":
            days = days_in_range(start, end)
            yesterday = self.today_fn() - timedelta(days=1)
            b_end = yesterday.isoformat()
            b_start = (yesterday - timedelta(days=days - 1)).isoformat()
            baseline = float(self.repo.sum_seconds(b_start, b_end,
                                                   website=website, application=app))
        else:  # last_week: same-length window shifted back 7 days
            baseline = float(self.repo.sum_seconds(
                shift_days(start, -7), shift_days(end, -7),
                website=website, application=app))
        result["baseline"] = baseline
        result["diff"] = seconds - baseline
        return result

    def _range(self, period: str) -> tuple[str, str]:
        return period_to_range(period, self.today_fn())
