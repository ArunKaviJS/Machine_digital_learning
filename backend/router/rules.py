"""Rule-based intent matching (SKILL §10) — data tables, no I/O.

normalise → detect intent (pattern scoring) → extract slots (aliases, periods).
Ambiguity (tie between intents, or a slot the rules cannot fill) → return None
so the caller hands the text to the AI (M7) or to clarification.
"""

from __future__ import annotations

import re
from typing import Any

FILLER_WORDS = {"bro", "arun", "please", "hey", "hi", "hello", "ok", "so", "yeah"}

SITE_ALIASES: dict[str, str] = {
    "yt": "youtube.com",
    "you tube": "youtube.com",
    "youtube": "youtube.com",
    "insta": "instagram.com",
    "ig": "instagram.com",
    "instagram": "instagram.com",
}

ANY_WORDS = {"any", "everything", "all", "overall", "total", "computer", "pc"}

# (regex, period) — longest phrases first so "last week" beats "week"
PERIOD_WORDS: list[tuple[str, str]] = [
    (r"\bpast 7 days\b", "last_7_days"),
    (r"\blast 7 days\b", "last_7_days"),
    (r"\blast week\b", "last_week"),
    (r"\bthis week\b", "this_week"),
    (r"\bthis month\b", "this_month"),
    (r"\byesterday\b", "yesterday"),
    (r"\btoday\b", "today"),
]

# "subject vs comparison-target": maps target phrase -> comparison enum
COMPARISON_RE = re.compile(
    r"\b(?:than|vs|versus|compared? to|compared? with|from|with) "
    r"(yesterday|last week|this week|today)\b"
)
COMPARISON_MAP = {"yesterday": "yesterday", "last week": "last_week",
                  "today": "none", "this week": "\x00invalid"}

FOLDER_ALIASES = {"download": "downloads", "downloads": "downloads",
                  "desktop": "desktop", "document": "documents",
                  "documents": "documents", "picture": "pictures",
                  "pictures": "pictures", "photo": "pictures", "pics": "pictures",
                  "video": "videos", "videos": "videos"}

INTENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "usage_query": (r"\bhow much\b", r"\bhow long\b", r"\bhow many\b",
                    r"\btime spent\b", r"\busage\b"),
    "compare_usage": (r"\bcompare\b", r"\bmore than\b", r"\bless than\b",
                      r"\bthan\b", r"\bvs\b", r"\bversus\b", r"\baverage\b",
                      r"\busual\b", r"\bnormal\b"),
    "top_app": (r"\bmost used\b", r"\bused the most\b", r"\buse the most\b",
                r"\btop app\b", r"\bwhat app\b", r"\bwhich app\b",
                r"\bfavourite app\b"),
    "screen_time": (r"\bscreen time\b", r"\bscreen on\b"),
    "longest_session": (r"\blongest\b",),
    "most_active_hour": (r"\bmost active\b", r"\bbusiest\b", r"\bactive hour\b"),
    "water_status": (r"\bwater\b", r"\bdrink\b", r"\bglass(?:es)?\b", r"\bhydrat"),
    "log_water": (r"\bdrank\b", r"\bdrunk\b", r"\bhad .{0,15}glass\b",
                  r"\bhad .{0,15}water\b", r"\bpoured\b"),
    "tidy_folder": (r"\btidy\b", r"\borgani[sz]e\b", r"\bclean\b", r"\bsort\b",
                    r"\bdeclutter\b"),
    "undo_tidy": (r"\bundo\b", r"\bput .*back\b", r"\brevert\b", r"\brestore\b"),
    "last_water_reminder": (r"\blast reminder\b", r"\breminder\b.*\bwater\b",
                            r"\bwater\b.*\breminder\b"),
    "open_site": (r"\bopen\b", r"\blaunch\b", r"\bgo to\b", r"\bpull up\b"),
    # deliberately tight: bare "close"/"shut" also appears in "close to",
    # "close enough" etc., and this intent fires a real Ctrl+W — require the
    # verb to be immediately followed by the site (or "tab"), not just
    # present anywhere in the sentence (SKILL §10 false-positive guard).
    "close_site_tab": (r"\bclose (the |that |this )?(youtube|instagram|insta|yt|ig)\b",
                       r"\bclose (the |that |this )?tab\b",
                       r"\bshut (the |that |this )?(youtube|instagram|insta|yt|ig)\b",
                       r"\bkill\b.*\btab\b"),
    # any installed/running app by name (resolved against the OS, not a list)
    "open_app": (r"\b(?:open|launch|fire up|pull up|bring up)\s+\w",),
    # same "close to"/"close enough" guard as close_site_tab: a lookahead
    # rejects the everyday senses of these verbs.
    "close_app": (r"\b(?:close|quit|exit|kill|shut down|shut)\s+"
                  r"(?!to\b|enough\b|by\b|up\b|in\b|on\b|call\b|down\b)\w",),
    # "change my wallpaper", "lower the brightness", "my eyes hurt from the
    # blue light" -> the matching Settings page (open-only, never toggled)
    "open_settings": (r"\bsettings?\b", r"\bnight light\b", r"\bblue light\b",
                      r"\b(?:change|adjust|set|increase|decrease|lower|raise|"
                      r"turn up|turn down|reduce|dim)\b.*\b(?:wallpaper|background|"
                      r"brightness|volume|sound|theme|dark mode|colou?rs?|"
                      r"resolution|display)\b"),
}

_OPEN_GROUP = {"open_site", "open_app", "open_settings"}
_CLOSE_GROUP = {"close_site_tab", "close_app"}

# target extraction runs on the RAW text: normalising would turn "github.com"
# into "github com" and "Notepad++" into "notepad".
_OPEN_TARGET_RE = re.compile(
    r"\b(?:open|launch|fire up|pull up|bring up|go to)\s+(?P<t>.+)$", re.I)
_CLOSE_TARGET_RE = re.compile(
    r"\b(?:close|quit|exit|kill|shut down|shut)\s+(?P<t>.+)$", re.I)
_TARGET_LEAD = re.compile(r"^(?:the|my|a|an|up)\s+", re.I)
_TARGET_TRAIL = re.compile(
    r"\s+(?:app|application|program|window|for me|now|right now|please|pls|"
    r"plz|bro|for me bro)$", re.I)


def _extract_target(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    target = m.group("t").strip().strip("\"'")
    target = re.sub(r"[\s?!,;:.]+$", "", target)
    previous = None
    while previous != target:
        previous = target
        target = _TARGET_TRAIL.sub("", _TARGET_LEAD.sub("", target)).strip()
    return target or None


def _resolve_open_close(winners: set[str], norm: str,
                        application: str | None) -> str | None:
    """Ties between open/close variants are decided by the slots, not by
    INTENT_TIES: a tracked site means the site/tab intent, otherwise the app."""
    if application == "any" and "open_settings" not in winners:
        return None  # "open everything" / "close all": too vague to act on
    has_site = application not in (None, "any")
    if winners <= _OPEN_GROUP:
        if "open_settings" in winners:
            return "open_settings"
        return "open_site" if has_site else "open_app"
    if winners <= _CLOSE_GROUP:
        if has_site or re.search(r"\btab\b", norm):
            return "close_site_tab"
        return "close_app"
    return None

# exact tie sets -> the intent that wins (everything else ambiguous -> AI)
INTENT_TIES: dict[frozenset[str], str] = {
    frozenset({"water_status", "log_water"}): "log_water",
    frozenset({"usage_query", "screen_time"}): "screen_time",
    frozenset({"water_status", "last_water_reminder"}): "last_water_reminder",
    frozenset({"usage_query", "compare_usage"}): "compare_usage",
}

# intents whose period defaults to today (SKILL §9)
PERIOD_INTENTS = {"usage_query", "compare_usage", "top_app", "screen_time",
                  "longest_session", "most_active_hour", "compare_days"}
NO_PERIOD_INTENTS = {"water_status", "log_water", "last_water_reminder",
                     "tidy_folder", "undo_tidy", "open_site", "close_site_tab",
                     "open_app", "close_app", "open_settings"}


def normalise(text: str) -> str:
    """lowercase, strip punctuation, drop filler words, collapse spaces."""
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    words = [w for w in cleaned.split() if w not in FILLER_WORDS]
    return " ".join(words)


def build_aliases(config: dict[str, Any]) -> dict[str, str]:
    """alias -> canonical site, from spec defaults + config siteMatchers."""
    aliases = dict(SITE_ALIASES)
    for site in config.get("siteMatchers", {}):
        aliases[site] = site
        aliases[site.split(".")[0]] = site
    return aliases


def _find_application(text: str, config: dict[str, Any]) -> str | None:
    if any(re.search(rf"\b{w}\b", text) for w in ANY_WORDS):
        return "any"
    aliases = build_aliases(config)
    best: tuple[int, str] | None = None
    for alias, site in aliases.items():
        m = re.search(rf"\b{re.escape(alias)}\b", text)
        if m and (best is None or len(alias) > best[0]):
            best = (len(alias), site)
    return best[1] if best else None


def _find_folder(text: str) -> str | None:
    for word, key in FOLDER_ALIASES.items():
        if re.search(rf"\b{word}\b", text):
            return key
    return None


def _find_periods(text: str) -> list[tuple[int, str]]:
    found = []
    for pattern, period in PERIOD_WORDS:
        for m in re.finditer(pattern, text):
            found.append((m.start(), period))
    return sorted(found)


def match_rules(text: str, config: dict[str, Any]) -> dict[str, Any] | None:
    """Normalised text -> intent dict (with slots) or None if unclear."""
    norm = normalise(text)
    if not norm:
        return None

    scores = {
        intent: sum(1 for p in patterns if re.search(p, norm))
        for intent, patterns in INTENT_PATTERNS.items()
    }
    scores = {k: v for k, v in scores.items() if v > 0}
    if not scores:
        return None
    top = max(scores.values())
    winners = [i for i, s in scores.items() if s == top]
    winners_set = set(winners)
    if winners_set <= _OPEN_GROUP or winners_set <= _CLOSE_GROUP:
        intent = _resolve_open_close(winners_set, norm, _find_application(norm, config))
        if intent is None:
            return None
    elif len(winners) > 1:
        if frozenset(winners) not in INTENT_TIES:
            return None  # ambiguity rule: hand off to AI
        intent = INTENT_TIES[frozenset(winners)]
    else:
        intent = winners[0]

    if intent in ("open_app", "close_app"):
        pattern = _OPEN_TARGET_RE if intent == "open_app" else _CLOSE_TARGET_RE
        target = _extract_target(pattern, text)
        if target is None:
            return None
        return {"intent": intent, "application": None, "period": None,
                "comparison": None, "folder": None, "target": target}
    if intent == "open_settings":
        return {"intent": intent, "application": None, "period": None,
                "comparison": None, "folder": None, "target": norm}

    # an explicit "I drank ..." marker turns a status hit into a log
    if intent == "water_status" and scores.get("log_water"):
        intent = "log_water"

    # comparison target ("than yesterday", "vs last week")
    comparison = None
    subject_text = norm
    comp = COMPARISON_RE.search(norm)
    if comp:
        comparison = COMPARISON_MAP[comp.group(1)]
        if comparison == "\x00invalid":
            return None
        subject_text = norm[:comp.start()] + " " + norm[comp.end():]

    periods = _find_periods(subject_text)
    period = periods[0][1] if periods else None

    application = _find_application(subject_text, config)
    folder = _find_folder(norm) if intent == "tidy_folder" else None

    # ambiguity rules (SKILL §10): required slots must be fillable here.
    # compare with an explicit target ("vs yesterday") but no site = overall
    # screen time; a bare compare phrase without period/app goes to the AI.
    if intent in ("usage_query", "compare_usage") and application is None:
        if intent == "compare_usage" and comp is not None:
            application = "any"
        else:
            return None
    if intent == "tidy_folder" and folder is None:
        return None
    if intent in ("open_site", "close_site_tab") and (
        application is None or application == "any"
    ):
        return None  # a specific tracked site is required

    return {
        "intent": intent,
        "application": application,
        "period": period,
        "comparison": comparison,
        "folder": folder,
    }
