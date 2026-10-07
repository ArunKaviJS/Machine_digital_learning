"""Quick Questions: catalogue (§8, single source of truth) + handlers.

Quick questions never touch the router or AI: question_id → service → template.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from backend.db.connection import Database
from backend.db.repositories.water_repo import WaterRepo
from backend.router import templates
from backend.services.periods import period_to_range
from backend.services.stats_service import StatsService
from backend.services.usage_service import UsageService

# SKILL §8 — IDs are contract, do not rename.
QUICK_QUESTIONS: list[dict[str, str]] = [
    {"id": "youtube_usage_today", "label": "How much YouTube did I use today?", "category": "USAGE"},
    {"id": "youtube_usage_yesterday", "label": "How much YouTube did I use yesterday?", "category": "USAGE"},
    {"id": "youtube_usage_week", "label": "How much YouTube did I use this week?", "category": "USAGE"},
    {"id": "top_app_today", "label": "What app did I use the most today?", "category": "PRODUCTIVITY"},
    {"id": "top_app_week", "label": "What app did I use the most this week?", "category": "PRODUCTIVITY"},
    {"id": "screen_time_today", "label": "How much screen time did I have today?", "category": "PRODUCTIVITY"},
    {"id": "longest_session_today", "label": "What was my longest session?", "category": "PRODUCTIVITY"},
    {"id": "most_active_hour_today", "label": "When was I most active today?", "category": "PRODUCTIVITY"},
    {"id": "compare_today_yesterday", "label": "How does today compare with yesterday?", "category": "PRODUCTIVITY"},
    {"id": "water_today", "label": "How much water did I drink today?", "category": "WATER"},
    {"id": "last_water_reminder", "label": "When was my last water reminder?", "category": "WATER"},
]

KNOWN_IDS = [q["id"] for q in QUICK_QUESTIONS]


class UnknownQuestion(Exception):
    pass


def _site_label(site: str, config: dict[str, Any]) -> str:
    keywords = config.get("siteMatchers", {}).get(site, [])
    return keywords[0] if keywords else site


def quick_answer(question_id: str, db: Database, config: dict[str, Any],
                 today: date | None = None) -> dict[str, Any]:
    """Full response envelope for one quick question (SKILL §18)."""
    if question_id not in KNOWN_IDS:
        raise UnknownQuestion(question_id)
    today = today or date.today()
    today_fn = lambda: today  # noqa: E731
    usage = UsageService(db, today_fn)
    stats = StatsService(db, today_fn)
    water = WaterRepo(db)

    yesterday = (today - timedelta(days=1)).isoformat()
    today_iso = today.isoformat()

    def yt_answer(period: str, label: str) -> dict:
        secs = usage.usage(period, site="youtube.com")["seconds"]
        data = {"seconds": secs, "site_label": _site_label("youtube.com", config),
                "period_label": label, "period": period}
        return {"data": data, "render": question_id}

    handlers: dict[str, Callable] = {
        "youtube_usage_today": lambda: yt_answer("today", "today"),
        "youtube_usage_yesterday": lambda: yt_answer("yesterday", "yesterday"),
        "youtube_usage_week": lambda: yt_answer("this_week", "this week"),
        "top_app_today": lambda: _top(usage.top_app("today"), "today"),
        "top_app_week": lambda: _top(usage.top_app("this_week"), "this week"),
        "screen_time_today": lambda: {"data": {"seconds": usage.screen_time("today")["seconds"]}},
        "longest_session_today": lambda: _longest(usage.longest_session("today"), config),
        "most_active_hour_today": lambda: {"data": usage.most_active_hour("today") or {"hour": None}},
        "compare_today_yesterday": lambda: _compare(stats, today_iso, yesterday),
        "water_today": lambda: {"data": {"count": water.count_drunk(today_iso),
                                         "target": config.get("waterDailyTarget", 8)}},
        "last_water_reminder": lambda: _last_reminder(water),
    }
    result = handlers[question_id]()
    data = result["data"]
    text, animation = templates.render(question_id, data)
    return {
        "text": text,
        "animation": animation,
        "needs_confirmation": False,
        "proposal_id": None,
        "data": data,
    }


def _top(row: dict | None, label: str) -> dict:
    if row is None:
        return {"data": {"application": None, "seconds": None, "period_label": label}}
    return {"data": {"application": row["application"], "seconds": row["seconds"],
                     "period_label": label, "period": row["period"]}}


def _longest(row: dict | None, config: dict) -> dict:
    if row is None:
        return {"data": {"seconds": None}}
    site = row.get("website")
    return {"data": {"seconds": row["seconds"], "application": row["application"],
                     "site_label": _site_label(site, config) if site else None}}


def _compare(stats: StatsService, today_iso: str, yesterday_iso: str) -> dict:
    result = stats.compare_days(today_iso, yesterday_iso)
    return {"data": {"today_seconds": result["a_seconds"],
                     "yesterday_seconds": result["b_seconds"],
                     "diff": result["diff"]}}


def _last_reminder(water: WaterRepo) -> dict:
    row = water.last_of_type("reminder_shown")
    return {"data": {"time": templates.fmt_clock(row["timestamp"]) if row else None,
                     "date": row["date"] if row else None}}
