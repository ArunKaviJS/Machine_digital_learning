"""Intent validation + defaults (SKILL §9) — applied to rules AND AI output."""

from __future__ import annotations

from typing import Any

from backend.config import KNOWN_INTENTS, TIDY_FOLDER_KEYS, VALID_COMPARISONS, VALID_PERIODS

# intents that take a period (default today per §9)
PERIOD_INTENTS = {"usage_query", "compare_usage", "top_app", "screen_time",
                  "longest_session", "most_active_hour", "compare_days"}

# open/close anything by name: a free-text `target` slot instead of the
# tracked-site whitelist; matched against what's actually installed/running.
TARGET_INTENTS = {"open_app", "close_app", "open_settings"}
MAX_TARGET_CHARS = 80


def _validate_target_intent(intent: str, raw: dict[str, Any]) -> dict[str, Any] | None:
    target = raw.get("target")
    if target is not None:
        if not isinstance(target, str):
            return None
        target = " ".join(target.split())[:MAX_TARGET_CHARS] or None
    if target is None and intent != "open_settings":  # settings alone = main page
        return None
    return {"intent": intent, "application": None, "period": None,
            "comparison": None, "folder": None, "target": target}


def tracked_applications(config: dict[str, Any]) -> set[str]:
    sites = set(config.get("distractingSites", [])) | set(config.get("siteMatchers", {}))
    return {s.lower() for s in sites}


def validate_intent(raw: Any, config: dict[str, Any]) -> dict[str, Any] | None:
    """Raw (possibly untrusted) intent -> normalised dict, or None if invalid.

    Result shape: {intent, application, period, comparison, folder}, plus
    `target` for TARGET_INTENTS (open/close app, open settings).
    """
    if not isinstance(raw, dict):
        return None
    intent = raw.get("intent")
    if not isinstance(intent, str) or intent not in KNOWN_INTENTS or intent == "unknown":
        return None
    if intent in TARGET_INTENTS:
        return _validate_target_intent(intent, raw)

    period = raw.get("period")
    if period is not None and not isinstance(period, str):
        return None
    if intent in PERIOD_INTENTS:
        period = period or "today"
        if period not in VALID_PERIODS:
            return None
    else:
        period = None  # not applicable for water/tidy intents

    comparison = raw.get("comparison")
    if intent in ("compare_usage", "compare_days"):
        comparison = comparison or ("yesterday" if intent == "compare_days" else "average")
        if comparison not in VALID_COMPARISONS:
            return None
    else:
        comparison = None

    application = raw.get("application")
    if application is not None:
        if not isinstance(application, str):
            return None
        application = application.strip().lower()
        if application == "":
            application = None
    if intent in ("usage_query", "compare_usage", "compare_days") and application is None:
        return None  # required slot
    if application is not None and application != "any":
        tracked = tracked_applications(config)
        if application not in tracked:
            # canonicalise friendly names: "youtube" -> "youtube.com"
            for site in tracked:
                if site.split(".")[0] == application:
                    application = site
                    break
        if application not in tracked:
            return None  # whitelist check: only tracked sites (or "any")
    if intent in ("open_site", "close_site_tab") and (
        application is None or application == "any"
    ):
        return None  # a specific tracked site is required

    folder = raw.get("folder")
    if intent in ("tidy_folder",):
        if not isinstance(folder, str):
            return None
        folder = folder.strip().lower()
        if folder not in TIDY_FOLDER_KEYS:
            return None
    else:
        folder = None

    return {"intent": intent, "application": application, "period": period,
            "comparison": comparison, "folder": folder}
