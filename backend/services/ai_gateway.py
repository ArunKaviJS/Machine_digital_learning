"""OllamaGateway (SKILL §11): text -> validated intent, logged to ai_calls.

Ollama only suggests; validate_intent (shared with the rules path) decides.
On any failure -> None -> router falls back to clarification.
"""

from __future__ import annotations

import datetime
import json
import time
from typing import Any, Callable

from backend.db.connection import Database
from backend.db.repositories.ai_repo import AiRepo
from backend.router.intent import validate_intent

from ai.prompts import build_messages
from ai.ollama_client import OllamaClient

MAX_TEXT_CHARS = 300


class OllamaGateway:
    def __init__(self, db: Database, config: dict[str, Any],
                 client: Any | None = None,
                 clock: Callable[[], float] = time.time):
        self.db = db
        self.config = config
        self.client = client if client is not None else OllamaClient(config)
        self.clock = clock

    def parse_intent(self, text: str) -> dict[str, Any] | None:
        ai = self.config.get("ai", {})
        if not ai.get("enabled"):
            return None
        text = text[:MAX_TEXT_CHARS]
        messages = build_messages(text, self.config)

        started = time.monotonic()
        response = self.client.chat(messages)
        latency_ms = int((time.monotonic() - started) * 1000)

        intent = self._validate(response, text)
        AiRepo(self.db).log_call(
            timestamp=datetime.datetime.now().astimezone()
                      .isoformat(timespec="seconds"),
            intent=intent["intent"] if intent else None,
            latency_ms=latency_ms,
            success=intent is not None,
            prompt=text if ai.get("logPrompts") else None,
        )
        return intent

    def _validate(self, response: Any, text: str = "") -> dict[str, Any] | None:
        """Ollama response dict -> validated intent, or None at any failure."""
        try:
            content = response["message"]["content"]
            parsed = json.loads(content)
        except (TypeError, KeyError, ValueError, json.JSONDecodeError):
            return None
        # The small model reliably picks open/close-app but often drops the
        # name. Then the user's own words become the target and the launcher
        # finds the installed/running app mentioned in them (code, not LLM).
        if (isinstance(parsed, dict) and parsed.get("intent") in ("open_app", "close_app")
                and not parsed.get("target")):
            parsed["target"] = text
        return validate_intent(parsed, self.config)
