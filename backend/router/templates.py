"""Response templates (SKILL §19): friendly text + animation from real data.

Pure functions: everything comes in via `data`, nothing reads the DB.
Tone: short, friendly, calls the user "bro" now and then.
"""

from __future__ import annotations

from datetime import datetime

WARN_SECONDS = 7200        # >= 2h on one thing -> warn pose
WARN_SCREEN_SECONDS = 21600  # >= 6h screen time -> warn pose


def fmt_duration(minutes: int | float | None) -> str:
    """SKILL §19: 155 -> '2h 35m', 45 -> '45m', 0 -> '0m'. Input is MINUTES."""
    if minutes is None:
        return "0m"
    total = int(round(minutes))
    if total < 60:
        return f"{total}m"
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    return f"{hours}h"


def fmt_secs(seconds: int | float | None) -> str:
    """Convenience: seconds from the DB -> '2h 35m' style text."""
    if seconds is None:
        return "0m"
    return fmt_duration(round(seconds / 60))


def fmt_hour(hour: int) -> str:
    """0 -> '12 AM', 13 -> '1 PM'."""
    suffix = "AM" if hour < 12 else "PM"
    h = hour % 12 or 12
    return f"{h} {suffix}"


def fmt_clock(iso_timestamp: str | None) -> str | None:
    """'2026-10-07T14:03:00+05:30' -> '14:03'."""
    if not iso_timestamp:
        return None
    try:
        return datetime.fromisoformat(iso_timestamp).strftime("%H:%M")
    except ValueError:
        return None


def _usage(data: dict) -> tuple[str, str]:
    secs = data["seconds"]
    site, label = data["site_label"], data["period_label"]
    if secs <= 0:
        return f"You haven't used {site} at all {label}, bro. Nice work!", "happy"
    animation = "warn" if secs >= WARN_SECONDS else "smile"
    return f"You spent {fmt_secs(secs)} on {site} {label}.", animation


def _top_app(data: dict) -> tuple[str, str]:
    app, secs, label = data.get("application"), data.get("seconds"), data["period_label"]
    if not app:
        return f"I don't have any app data for {label} yet, bro.", "idle"
    return (f"{app} was your most used app {label} — {fmt_secs(secs)} on it.",
            "smile")


def _screen_time(data: dict) -> tuple[str, str]:
    secs = data["seconds"]
    if secs <= 0:
        return "No screen time recorded today yet, bro.", "happy"
    animation = "warn" if secs >= WARN_SCREEN_SECONDS else "smile"
    return f"You had {fmt_secs(secs)} of screen time today.", animation


def _longest_session(data: dict) -> tuple[str, str]:
    secs = data.get("seconds")
    if not secs:
        return "I don't have any sessions recorded today yet, bro.", "idle"
    app, site = data["application"], data.get("site_label")
    if site:
        text = f"Your longest session today was {fmt_secs(secs)} on {site} ({app})."
    else:
        text = f"Your longest session today was {fmt_secs(secs)} in {app}."
    return text, "smile"


def _most_active_hour(data: dict) -> tuple[str, str]:
    hour = data.get("hour")
    if hour is None:
        return "I don't have any activity for today yet, bro.", "idle"
    return (f"You were most active around {fmt_hour(hour)} today "
            f"({fmt_secs(data['seconds'])} of activity).", "smile")


def _compare_today_yesterday(data: dict) -> tuple[str, str]:
    diff = data["diff"]
    today = fmt_secs(data["today_seconds"])
    if diff == 0:
        return f"You've had {today} of screen time today — exactly the same as yesterday, bro.", "smile"
    if diff > 0:
        return (f"You've had {today} of screen time today, "
                f"{fmt_secs(diff)} more than yesterday.", "warn")
    return (f"You've had {today} of screen time today, "
            f"{fmt_secs(abs(diff))} less than yesterday.", "happy")


def _water_today(data: dict) -> tuple[str, str]:
    count, target = data["count"], data["target"]
    if count >= target:
        return f"Target hit, bro! {count} glasses of water today.", "happy"
    if count == 0:
        return f"You haven't had any water today yet, bro. The goal is {target} glasses.", "water"
    return f"You've had {count} of {target} glasses today.", "water"


def _last_water_reminder(data: dict) -> tuple[str, str]:
    time = data.get("time")
    if not time:
        return "I haven't shown a water reminder yet, bro.", "water"
    return f"Your last water reminder was at {time}.", "water"


RENDERERS = {
    "youtube_usage_today": _usage,
    "youtube_usage_yesterday": _usage,
    "youtube_usage_week": _usage,
    "top_app_today": _top_app,
    "top_app_week": _top_app,
    "screen_time_today": _screen_time,
    "longest_session_today": _longest_session,
    "most_active_hour_today": _most_active_hour,
    "compare_today_yesterday": _compare_today_yesterday,
    "water_today": _water_today,
    "last_water_reminder": _last_water_reminder,
}


def render(question_id: str, data: dict) -> tuple[str, str]:
    """(text, animation) for a quick question. Raises KeyError if unknown."""
    return RENDERERS[question_id](data)


# ---------------------------------------------------------------------------
# Free-text intent renderers (router step 3). Data is assembled by the router
# from service output + config labels; renderers only format.
# ---------------------------------------------------------------------------

PERIOD_LABELS = {"today": "today", "yesterday": "yesterday",
                 "this_week": "this week", "last_week": "last week",
                 "last_7_days": "the last 7 days", "this_month": "this month"}


def period_label(period: str | None) -> str:
    if not period:
        return "today"
    return PERIOD_LABELS.get(period, period.replace("_", " "))


def _i_usage(data: dict) -> tuple[str, str]:
    return _usage(data)


def _i_top_app(data: dict) -> tuple[str, str]:
    return _top_app(data)


def _i_screen_time(data: dict) -> tuple[str, str]:
    secs, label = data["seconds"], data["period_label"]
    if secs <= 0:
        return f"No screen time recorded {label} yet, bro.", "happy"
    animation = "warn" if secs >= WARN_SCREEN_SECONDS else "smile"
    return f"You had {fmt_secs(secs)} of screen time {label}.", animation


def _i_longest_session(data: dict) -> tuple[str, str]:
    secs = data.get("seconds")
    label = data["period_label"]
    if not secs:
        return f"I don't have any sessions recorded {label} yet, bro.", "idle"
    app, site = data["application"], data.get("site_label")
    if site:
        text = f"Your longest session {label} was {fmt_secs(secs)} on {site} ({app})."
    else:
        text = f"Your longest session {label} was {fmt_secs(secs)} in {app}."
    return text, "smile"


def _i_most_active_hour(data: dict) -> tuple[str, str]:
    hour, label = data.get("hour"), data["period_label"]
    if hour is None:
        return f"I don't have any activity for {label} yet, bro.", "idle"
    return (f"You were most active around {fmt_hour(hour)} {label} "
            f"({fmt_secs(data['seconds'])} of activity).", "smile")


def _i_compare_usage(data: dict) -> tuple[str, str]:
    site, label = data["site_label"], data["period_label"]
    dur = fmt_secs(data["seconds"])
    baseline, diff, base_label = data["baseline"], data["diff"], data["baseline_label"]
    if baseline is None:
        return f"You spent {dur} on {site} {label}.", "smile"
    if diff == 0:
        return (f"You spent {dur} on {site} {label} — same as {base_label}, "
                f"bro."), "smile"
    if diff > 0:
        return (f"You spent {dur} on {site} {label}, {fmt_secs(diff)} more "
                f"than {base_label}.", "warn")
    return (f"You spent {dur} on {site} {label}, {fmt_secs(abs(diff))} less "
            f"than {base_label}.", "happy")


def _i_log_water(data: dict) -> tuple[str, str]:
    count, target = data["count"], data["target"]
    if count >= target:
        return f"Cheers! That's {count} of {target} glasses — target hit, bro!", "happy"
    return f"Cheers! That's {count} of {target} glasses today, bro.", "happy"


def _i_last_water_reminder(data: dict) -> tuple[str, str]:
    return _last_water_reminder(data)


def _i_open_site(data: dict) -> tuple[str, str]:
    site = data["site_label"]
    if data.get("opened"):
        return f"Opening {site} for you, bro!", "working"
    return f"Couldn't open {site} right now, bro.", "warn"


def _i_close_site_tab(data: dict) -> tuple[str, str]:
    site = data["site_label"]
    if data.get("closed"):
        return f"Closed the {site} tab, bro.", "happy"
    if data.get("reason") == "not_foreground":
        return f"I don't see {site} up front right now, bro — nothing to close.", "idle"
    return f"Couldn't close {site} right now, bro.", "warn"


def _i_open_app(data: dict) -> tuple[str, str]:
    status, name, query = data.get("status"), data.get("name"), data.get("query")
    if status == "opened":
        return f"Opening {name} for you, bro!", "working"
    if status == "opened_url":
        return f"Opening {name} in your browser, bro!", "working"
    if status == "not_found":
        if len((query or "").split()) > 3:  # a whole sentence, not an app name
            return "I couldn't find that app on this PC, bro.", "confused"
        return f"I couldn't find an app called '{query}' on this PC, bro.", "confused"
    return f"Tried to open {name or query}, but Windows didn't let me, bro.", "warn"


def _i_close_app(data: dict) -> tuple[str, str]:
    status, name, query = data.get("status"), data.get("name"), data.get("query")
    if status == "closed":
        count = data.get("count", 1)
        windows = f" ({count} windows)" if count > 1 else ""
        return (f"Closing {name}{windows}, bro. If there's unsaved work, "
                f"it'll ask you first."), "happy"
    if status == "not_running":
        if len((query or "").split()) > 3:
            return "I don't see that app open right now, bro.", "idle"
        return f"'{query}' isn't open right now, bro.", "idle"
    return f"Couldn't close {name or query}, bro — it may be running as admin.", "warn"


def _i_open_settings(data: dict) -> tuple[str, str]:
    page = data.get("page", "settings")
    if data.get("status") != "opened":
        return "Couldn't open Settings, bro.", "warn"
    if page in ("night light", "blue light"):
        return ("Opened Night light settings — Windows doesn't let apps flip it "
                "directly, so hit the toggle there, bro."), "working"
    if page == "settings":
        return "Opening Settings, bro.", "working"
    return f"Opening {page} settings, bro.", "working"


INTENT_RENDERERS = {
    "usage_query": _i_usage,
    "top_app": _i_top_app,
    "screen_time": _i_screen_time,
    "longest_session": _i_longest_session,
    "most_active_hour": _i_most_active_hour,
    "compare_usage": _i_compare_usage,
    "compare_days": _i_compare_usage,
    "water_status": _water_today,
    "log_water": _i_log_water,
    "last_water_reminder": _i_last_water_reminder,
    "open_site": _i_open_site,
    "close_site_tab": _i_close_site_tab,
    "open_app": _i_open_app,
    "close_app": _i_close_app,
    "open_settings": _i_open_settings,
}


def render_intent(intent: dict, data: dict) -> tuple[str, str]:
    """(text, animation) for a free-text intent. KeyError if unknown intent."""
    return INTENT_RENDERERS[intent["intent"]](data)
