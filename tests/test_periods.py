"""Tests for backend/services/periods.py."""

from __future__ import annotations

from datetime import date

import pytest

from backend.services.periods import days_in_range, period_to_range, shift_days

TODAY = date(2026, 10, 7)   # Wednesday


def test_today_and_yesterday():
    assert period_to_range("today", TODAY) == ("2026-10-07", "2026-10-07")
    assert period_to_range("yesterday", TODAY) == ("2026-10-06", "2026-10-06")


def test_this_week_starts_monday():
    start, end = period_to_range("this_week", TODAY)
    assert date.fromisoformat(start).weekday() == 0   # Monday
    assert start == "2026-10-05"                      # Monday of that week
    assert end == "2026-10-07"


def test_last_week_is_full_monday_to_sunday():
    start, end = period_to_range("last_week", TODAY)
    assert start == "2026-09-28"
    assert end == "2026-10-04"
    assert date.fromisoformat(start).weekday() == 0
    assert date.fromisoformat(end).weekday() == 6
    assert days_in_range(start, end) == 7


def test_last_7_days_includes_today():
    start, end = period_to_range("last_7_days", TODAY)
    assert start == "2026-10-01"
    assert end == "2026-10-07"
    assert days_in_range(start, end) == 7


def test_this_month():
    assert period_to_range("this_month", TODAY) == ("2026-10-01", "2026-10-07")


def test_week_start_on_a_monday():
    monday = date(2026, 10, 5)
    assert period_to_range("this_week", monday) == ("2026-10-05", "2026-10-05")
    assert period_to_range("last_week", monday) == ("2026-09-28", "2026-10-04")


def test_unknown_period_raises():
    with pytest.raises(ValueError):
        period_to_range("fortnight", TODAY)


def test_default_today_is_real_today():
    from datetime import date as _date
    assert period_to_range("today")[0] == _date.today().isoformat()


def test_shift_days():
    assert shift_days("2026-10-07", -7) == "2026-09-30"
    assert shift_days("2026-03-01", 1) == "2026-03-02"
