"""Ollama HTTP client (SKILL §11): one request shape, single-flight, no raise."""

from __future__ import annotations

import threading
from typing import Any

import httpx

from ai.prompts import intent_schema


class OllamaClient:
    """POST {host}/api/chat. Returns the parsed response dict or None.

    Single-flight: a threading.Lock serialises calls — the second caller
    waits for the first (one model, one GPU/CPU — parallel calls just queue).
    keep_alive comes from config ai.keepAlive ("5m" keeps the model warm).
    Never raises: timeout / connection error / bad status -> None.
    """

    def __init__(self, cfg: dict[str, Any], post=httpx.post):
        self.cfg = cfg
        self._post = post
        self._lock = threading.Lock()

    @property
    def ai(self) -> dict[str, Any]:
        return self.cfg.get("ai", {})

    def chat(self, messages: list[dict[str, str]]) -> dict[str, Any] | None:
        payload = {
            "model": self.ai.get("model", "qwen2.5:0.5b-instruct"),
            "messages": messages,
            "stream": False,
            "format": intent_schema(self.cfg),
            "keep_alive": self.ai.get("keepAlive", 0),
            "options": {
                "temperature": 0,
                "num_predict": 120,
                "num_ctx": 1024,
            },
        }
        url = f"{self.ai.get('host', 'http://localhost:11434').rstrip('/')}/api/chat"
        timeout = float(self.ai.get("timeoutSeconds", 15))
        with self._lock:
            try:
                resp = self._post(url, json=payload, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except Exception:
                return None
