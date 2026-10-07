"""Tests for UsageService + StatsService against seeded rows."""

from __future__ import annotations

from datetime import date

import pytest

from backend.db.connection import Database
from backend.db.migrations import migrate
from backend.db.repositories.usage_repo import UsageRepo
from backend.services.stats_service import StatsService
from backend.services.usage_service import UsageService

TODAY = date(2026, 10, 7)  # Wednesday; Monday = 2026-10-05, last week = 09-28..10-04


@pytest.fixture()
def services():
    db = Database(":memory:")
    migrate(db.raw)
    repo = UsageRepo(db)

    def add(day, hour, app, seconds, website=None):
        start = f"{day}T{hour:02d}:00:00+05:30"
        end = f"{day}T{hour:02d}:00:00+05:30"
        repo.insert_session(app, start, end, seconds, day, website=website)

    add("2026-10-07", 9, "Chrome", 3600, website="youtube.com")
    add("2026-10-07", 14, "Code", 1800)
    add("2026-10-06", 11, "Chrome", 1800, website="youtube.com")
    add("2026-10-06", 15, "Code", 3600)
    add("2026-10-05", 8, "Chrome", 600, website="youtube.com")
    add("2026-10-01", 10, "Chrome", 1200, website="instagram.com")
    add("2026-09-30", 19, "Chrome", 7200, website="youtube.com")

    today_fn = lambda: TODAY  # noqa: E731
    yield UsageService(db, today_fn), StatsService(db, today_fn), db
    db.close()


@pytest.fixture()
def usage(services):
    return services[0]


@pytest.fixture()
def stats(services):
    return services[1]


# ---- UsageService ----

def test_usage_today_and_yesterday(usage):
    assert usage.usage("today", site="youtube.com")["seconds"] == 3600
    assert usage.usage("today", app="Code")["seconds"] == 1800
    assert usage.usage("yesterday", site="youtube.com")["seconds"] == 1800
    assert usage.usage("today", site="instagram.com")["seconds"] == 0


def test_screen_time(usage):
    assert usage.screen_time("today")["seconds"] == 5400
    assert usage.screen_time("this_week")["seconds"] == 11400
    assert usage.screen_time("last_week")["seconds"] == 8400
    assert usage.screen_time("this_month")["seconds"] == 12600
    assert usage.screen_time("last_7_days")["seconds"] == 12600


def test_top_app(usage):
    assert usage.top_app("today") == {"period": "today", "application": "Chrome",
                                      "seconds": 3600}
    assert usage.top_app("this_week")["seconds"] == 6000
    assert usage.top_app("yesterday")["application"] == "Code"


def test_longest_session_and_active_hour(usage):
    longest = usage.longest_session("today")
    assert longest["seconds"] == 3600
    assert longest["website"] == "youtube.com"
    hour = usage.most_active_hour("today")
    assert hour["hour"] == 9 and hour["seconds"] == 3600


def test_unknown_period_raises(usage):
    with pytest.raises(ValueError):
        usage.usage("fortnight")


# ---- StatsService ----

def test_compare_days(stats):
    result = stats.compare_days("2026-10-07", "2026-10-06")
    assert result["a_seconds"] == 5400 and result["b_seconds"] == 5400
    assert result["diff"] == 0 and result["equal"] is True

    yt = stats.compare_days("2026-10-07", "2026-10-06", website="youtube.com")
    assert yt["a_seconds"] == 3600 and yt["b_seconds"] == 1800
    assert yt["diff"] == 1800 and yt["more"] is True


def test_average_daily_excludes_today(stats):
    # youtube: Sep30=7200, Oct5=600, Oct6=1800 -> 9600 / 7 (Oct7 NOT counted)
    assert stats.average_daily(website="youtube.com") == pytest.approx(9600 / 7)


def test_compare_usage_average(stats):
    result = stats.compare_usage("today", website="youtube.com", comparison="average")
    assert result["seconds"] == 3600
    assert result["baseline"] == pytest.approx(9600 / 7)
    assert result["diff"] == pytest.approx(3600 - 9600 / 7)


def test_compare_usage_yesterday(stats):
    result = stats.compare_usage("today", website="youtube.com", comparison="yesterday")
    assert result["seconds"] == 3600
    assert result["baseline"] == 1800
    assert result["diff"] == 1800


def test_compare_usage_last_week(stats):
    result = stats.compare_usage("today", website="youtube.com", comparison="last_week")
    assert result["baseline"] == 7200          # single day, same weekday last week
    assert result["diff"] == -3600

    week = stats.compare_usage("this_week", website="youtube.com", comparison="last_week")
    assert week["seconds"] == 6000             # Oct5..Oct7
    assert week["baseline"] == 7200            # Sep28..Oct4
    assert week["diff"] == -1200


def test_compare_usage_none(stats):
    result = stats.compare_usage("today", website="youtube.com", comparison="none")
    assert result["baseline"] is None and result["diff"] is None


def test_compare_usage_invalid_comparison(stats):
    with pytest.raises(ValueError):
        stats.compare_usage("today", website="youtube.com", comparison="tomorrow")
