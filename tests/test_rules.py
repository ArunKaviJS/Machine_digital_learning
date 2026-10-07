"""Table-driven tests for the rule-based router (SKILL §10)."""

from __future__ import annotations

import pytest

from backend.router.intent import validate_intent
from backend.router.rules import build_aliases, match_rules, normalise

CFG = {
    "siteMatchers": {"youtube.com": ["YouTube", "yt"],
                     "instagram.com": ["Instagram"]},
    "distractingSites": ["youtube.com", "instagram.com"],
    "waterDailyTarget": 8,
}


def run(text: str):
    """Full rules pipeline exactly as the router uses it."""
    return validate_intent(match_rules(text, CFG), CFG)


def I(intent, application=None, period="today", comparison=None, folder=None):
    return {"intent": intent, "application": application, "period": period,
            "comparison": comparison, "folder": folder}


# (phrase, expected full intent dict or None) — ~40 cases, §10 rules
TABLE = [
    # usage_query
    ("how much youtube did i use today", I("usage_query", "youtube.com")),
    ("how long did I use Instagram yesterday", I("usage_query", "instagram.com", "yesterday")),
    ("how many hours on youtube this week", I("usage_query", "youtube.com", "this_week")),
    ("what's my usage of youtube", I("usage_query", "youtube.com")),
    ("time spent on youtube today", I("usage_query", "youtube.com")),
    ("how much did I use youtube this month", I("usage_query", "youtube.com", "this_month")),
    ("how much youtube", I("usage_query", "youtube.com")),
    ("how much yt did i use today", I("usage_query", "youtube.com")),
    ("how long on ig yesterday", I("usage_query", "instagram.com", "yesterday")),
    ("how much time did I spend on the computer today", I("usage_query", "any")),
    # top_app
    ("what app did i use the most today", I("top_app")),
    ("most used app this week", I("top_app", None, "this_week")),
    ("what is my top app yesterday", I("top_app", None, "yesterday")),
    ("which app did I use the most", I("top_app")),
    # screen_time
    ("how much screen time today", I("screen_time")),
    ("screen time this week", I("screen_time", None, "this_week")),
    # longest_session / most_active_hour
    ("what was my longest session yesterday", I("longest_session", None, "yesterday")),
    ("longest session this week", I("longest_session", None, "this_week")),
    ("when was I most active today", I("most_active_hour")),
    ("busiest hour yesterday", I("most_active_hour", None, "yesterday")),
    # compare_usage
    ("how does today compare with yesterday",
     I("compare_usage", "any", "today", "yesterday")),
    ("compare youtube with last week",
     I("compare_usage", "youtube.com", "today", "last_week")),
    ("am i using more youtube than usual",
     I("compare_usage", "youtube.com", "today", "average")),
    ("was I on youtube more than yesterday",
     I("compare_usage", "youtube.com", "today", "yesterday")),
    ("instagram usage vs last week",
     I("compare_usage", "instagram.com", "today", "last_week")),
    ("compare this week with last week",
     I("compare_usage", "any", "this_week", "last_week")),
    # water
    ("how much water did I drink today", I("water_status", None, None)),
    ("am I hydrated enough", I("water_status", None, None)),
    ("water status", I("water_status", None, None)),
    ("I just drank a glass", I("log_water", None, None)),
    ("I had two glasses of water", I("log_water", None, None)),
    ("I drank water", I("log_water", None, None)),
    ("when was my last water reminder", I("last_water_reminder", None, None)),
    # tidy / undo
    ("organize my downloads", I("tidy_folder", None, None, None, "downloads")),
    ("tidy up my desktop", I("tidy_folder", None, None, None, "desktop")),
    ("clean my documents folder", I("tidy_folder", None, None, None, "documents")),
    ("sort my pictures", I("tidy_folder", None, None, None, "pictures")),
    ("declutter my videos", I("tidy_folder", None, None, None, "videos")),
    ("undo that", I("undo_tidy", None, None)),
    ("put it back", I("undo_tidy", None, None)),
    # open / close a tracked site
    ("open youtube", I("open_site", "youtube.com", None)),
    ("launch instagram", I("open_site", "instagram.com", None)),
    ("close the youtube tab", I("close_site_tab", "youtube.com", None)),
    ("shut instagram", I("close_site_tab", "instagram.com", None)),
    # any installed / running app (target matched against the OS later)
    ("open whatsapp", {**I("open_app", None, None), "target": "whatsapp"}),
    ("can you open Notepad for me?", {**I("open_app", None, None), "target": "Notepad"}),
    ("go to github.com", {**I("open_app", None, None), "target": "github.com"}),
    ("close whatsapp", {**I("close_app", None, None), "target": "whatsapp"}),
    ("quit the calculator app", {**I("close_app", None, None), "target": "calculator"}),
    ("turn on night light",
     {**I("open_settings", None, None), "target": "turn on night light"}),
    ("open bluetooth settings",
     {**I("open_settings", None, None), "target": "open bluetooth settings"}),
    # former LLM misses, now deterministic
    ("kill teams", {**I("close_app", None, None), "target": "teams"}),
    ("fire up teams please", {**I("open_app", None, None), "target": "teams"}),
    ("I want to change my wallpaper",
     {**I("open_settings", None, None), "target": "i want to change my wallpaper"}),
    ("my eyes hurt from the blue light",
     {**I("open_settings", None, None), "target": "my eyes hurt from the blue light"}),
    ("lower the brightness",
     {**I("open_settings", None, None), "target": "lower the brightness"}),
    ("kill the youtube tab", I("close_site_tab", "youtube.com", None)),
    # ambiguity / no match -> hand off to AI
    ("tell me a joke", None),
    ("ok", None),
    ("", None),
    ("open everything", None),                # no specific site to open
    # "close" as an ordinary word ("close to") must NOT trigger the
    # destructive close_site_tab action — regression for a false positive
    ("am I close to finishing my instagram post", None),
    ("is youtube close to done loading", None),
    ("close enough on instagram today", None),
    ("how much", None),                       # usage with no application
    ("tidy my folder", None),                 # tidy with no known folder
    ("was I wasting more time on videos than usual yesterday?", None),  # no tracked app
    ("how much github did i use today", None),  # app not in tracked list
]


@pytest.mark.parametrize("text,expected", TABLE)
def test_match_rules(text, expected):
    assert run(text) == expected


def test_normalise_strips_punctuation_and_fillers():
    assert normalise("Hey bro, how much YouTube?!") == "how much youtube"
    assert normalise("   ") == ""


def test_build_aliases_includes_config_sites():
    aliases = build_aliases(CFG)
    assert aliases["yt"] == "youtube.com"
    assert aliases["youtube"] == "youtube.com"
    assert aliases["insta"] == "instagram.com"
    assert aliases["instagram.com"] == "instagram.com"


def test_validate_rejects_bad_enum_and_unknown_intent():
    assert validate_intent({"intent": "launch_nuke"}, CFG) is None
    assert validate_intent({"intent": "unknown"}, CFG) is None
    assert validate_intent({"intent": "usage_query", "application": "youtube.com",
                            "period": "fortnight"}, CFG) is None
    assert validate_intent({"intent": "usage_query",
                            "application": "github.com"}, CFG) is None
    assert validate_intent("not a dict", CFG) is None


def test_validate_fills_defaults():
    got = validate_intent({"intent": "usage_query", "application": "YouTube"},
                          CFG)
    assert got == {"intent": "usage_query", "application": "youtube.com",
                   "period": "today", "comparison": None, "folder": None}
