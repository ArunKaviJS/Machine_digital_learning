"""Period → date-range helper. One place, unit-tested; week starts Monday."""

from __future__ import annotations

from datetime import date, timedelta

VALID_PERIODS = ("today", "yesterday", "this_week", "last_week",
                 "last_7_days", "this_month")


def period_to_range(period: str, today: date | None = None) -> tuple[str, str]:
    """ISO (start_date, end_date) inclusive for a period name."""
    today = today or date.today()
    if period == "today":
        start = end = today
    elif period == "yesterday":
        start = end = today - timedelta(days=1)
    elif period == "this_week":
        start = today - timedelta(days=today.weekday())  # Monday
        end = today
    elif period == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)                  # Sunday
    elif period == "last_7_days":
        start = today - timedelta(days=6)
        end = today
    elif period == "this_month":
        start = today.replace(day=1)
        end = today
    else:
        raise ValueError(f"unknown period: {period!r} (valid: {VALID_PERIODS})")
    return start.isoformat(), end.isoformat()


def days_in_range(start_iso: str, end_iso: str) -> int:
    return (date.fromisoformat(end_iso) - date.fromisoformat(start_iso)).days + 1


def shift_days(iso_date: str, days: int) -> str:
    return (date.fromisoformat(iso_date) + timedelta(days=days)).isoformat()
