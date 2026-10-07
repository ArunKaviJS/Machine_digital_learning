"""System prompt + few-shot examples (SKILL §11): text -> intent JSON only."""

from __future__ import annotations

from typing import Any

from backend.config import KNOWN_INTENTS, TIDY_FOLDER_KEYS, VALID_COMPARISONS, VALID_PERIODS

# SKILL §11: ~8 few-shot examples covering the main intents + one unknown
FEWSHOT: list[tuple[str, str]] = [
    ("how much youtube did i use today",
     '{"intent": "usage_query", "application": "youtube.com", "period": "today"}'),
    ("what's my screen time this week",
     '{"intent": "screen_time", "period": "this_week"}'),
    ("am I using more instagram than usual",
     '{"intent": "compare_usage", "application": "instagram.com", "period": "today", "comparison": "average"}'),
    ("which app did I use the most yesterday",
     '{"intent": "top_app", "period": "yesterday"}'),
    ("I just had a glass of water",
     '{"intent": "log_water"}'),
    ("how much water have I had today",
     '{"intent": "water_status"}'),
    ("tidy my downloads folder",
     '{"intent": "tidy_folder", "folder": "downloads"}'),
    ("undo that",
     '{"intent": "undo_tidy"}'),
    ("open youtube",
     '{"intent": "open_site", "application": "youtube.com"}'),
    ("close that instagram tab",
     '{"intent": "close_site_tab", "application": "instagram.com"}'),
    ("could you fire up spotify for me",
     '{"intent": "open_app", "target": "spotify"}'),
    ("get rid of the calculator window",
     '{"intent": "close_app", "target": "calculator"}'),
    ("my screen is too bright at night",
     '{"intent": "open_settings", "target": "night light"}'),
    ("tell me a joke",
     '{"intent": "unknown"}'),
]

USER_INSTRUCTION = ('Respond ONLY with JSON in exactly this shape: '
                    '{"intent": ..., "application": ..., "period": ..., '
                    '"comparison": ..., "folder": ..., "target": ...}. '
                    'If you are not sure, use {"intent": "unknown"}. '
                    'Never answer the question itself.')


def system_prompt(config: dict[str, Any]) -> str:
    """Short system prompt with the allowed enums + tracked sites (§11)."""
    sites = sorted(set(config.get("distractingSites", []))
                   | set(config.get("siteMatchers", {})))
    return (
        "You are the intent parser for a desktop companion called Arun. "
        "Convert the user question into intent JSON only.\n"
        f"Allowed intents: {', '.join(sorted(KNOWN_INTENTS))}.\n"
        f"Allowed periods: {', '.join(sorted(VALID_PERIODS))} "
        "(default today when the question implies now/today).\n"
        f"Allowed comparisons: {', '.join(sorted(VALID_COMPARISONS))}.\n"
        f"application: one of these tracked sites ({', '.join(sites)}) "
        'or "any" for everything; null if not a usage question.\n'
        f"folder: one of {', '.join(sorted(TIDY_FOLDER_KEYS))} "
        "only for tidy_folder.\n"
        'target: the app or settings page name, only for open_app, close_app '
        "and open_settings (e.g. \"whatsapp\", \"notepad\", \"bluetooth\").\n"
        f"{USER_INSTRUCTION}"
    )


def intent_schema(config: dict[str, Any]) -> dict[str, Any]:
    """JSON schema for Ollama structured outputs: generation is constrained to
    it, so the model cannot e.g. write an app name into `application` (only
    tracked sites are allowed there) — free text can only go in `target`."""
    sites = sorted(set(config.get("distractingSites", []))
                   | set(config.get("siteMatchers", {})))

    def nullable(values: list[str]) -> dict[str, Any]:
        return {"enum": [*values, None]}

    return {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": sorted(KNOWN_INTENTS)},
            "application": nullable([*sites, "any"]),
            "period": nullable(sorted(VALID_PERIODS)),
            "comparison": nullable(sorted(VALID_COMPARISONS)),
            "folder": nullable(sorted(TIDY_FOLDER_KEYS)),
            "target": {"type": ["string", "null"]},
        },
        "required": ["intent"],
    }


def build_messages(text: str, config: dict[str, Any]) -> list[dict[str, str]]:
    """[system] + few-shot pairs + [user] for POST /api/chat."""
    messages = [{"role": "system", "content": system_prompt(config)}]
    for question, answer in FEWSHOT:
        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": answer})
    messages.append({"role": "user", "content": text})
    return messages
