"""THE LLM FILE — the only module that talks to a language-model provider.

Every agent, the main agent's router and the intent gateway call the model
through `LLM` (get one with `get_llm(config)`). To switch provider (another
Ollama model, llama.cpp, a cloud API...) change ONLY this file: keep the
four public methods and their return shapes, and nothing else needs to
change.

Contract
--------
chat(messages, schema=None, model=None, num_predict=120, num_ctx=1024, timeout=None)
    messages: [{"role": "system"|"user"|"assistant", "content": str}, ...]
    schema:   JSON schema the reply must follow (structured output) or None
    returns:  {"message": {"content": "<the model's text / JSON>"}} or None on
              ANY failure (timeout, connection, bad status) — never raises.
choose(question, options, model=None) -> one of `options` or None
    a tiny constrained pick (the main agent's "which sub-agent?" call).
ping() -> bool        is the provider reachable right now? (cheap, never raises)
warm_up(models)       load models in the background so the first real
                      request isn't a 7-10 s cold start (never raises).
unload(models)        free the model's memory now (never raises). With
                      config ai.keepAlive (e.g. "2m") the provider also
                      unloads it by itself after that long without use.

Single-flight: one lock serialises calls (one GPU: parallel calls only
queue, and two agents can never interleave inside one model call).
Current provider: Ollama (http://localhost:11434, /api/chat, /api/tags).
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable

import httpx

logger = logging.getLogger("arun.llm")

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:1.5b"  # one model for everything (intents + all agents)
DEFAULT_TIMEOUT = 15.0
PING_TIMEOUT = 2.0
CHOOSE_TIMEOUT = 20.0
# ONE context size per model: Ollama reloads a model whenever a call asks
# for a different num_ctx (measured: 2.8 s warm -> 8.3 s after a switch), and
# the warm-up / "which agent?" / agent-loop calls used to differ.
INTENT_CTX = 1024    # the small intent model: short prompts
AGENT_CTX = 6144     # the agent model: tool catalog + conversation


class LLM:
    def __init__(self, cfg: dict[str, Any], post: Callable | None = None,
                 get: Callable | None = None):
        self.cfg = cfg
        self._post_fn = post  # injectable transport (tests); default httpx
        self._get_fn = get
        self._lock = threading.Lock()

    def _post(self, *args, **kwargs):
        return (self._post_fn or httpx.post)(*args, **kwargs)

    def _get(self, *args, **kwargs):
        return (self._get_fn or httpx.get)(*args, **kwargs)

    # ---- settings (config "ai" block) ----
    @property
    def ai(self) -> dict[str, Any]:
        return self.cfg.get("ai", {})

    @property
    def host(self) -> str:
        return str(self.ai.get("host", DEFAULT_HOST)).rstrip("/")

    def default_model(self) -> str:
        return self.ai.get("model", DEFAULT_MODEL)

    def agent_model(self) -> str:
        return self.ai.get("agent", {}).get("model") or self.default_model()

    def context_size(self, model: str) -> int:
        """The one num_ctx this model is always loaded with (no reloads)."""
        if model == self.agent_model():
            return int(self.ai.get("agent", {}).get("numCtx", AGENT_CTX))
        return int(self.ai.get("numCtx", INTENT_CTX))

    # ---- the contract ----
    def chat(self, messages: list[dict[str, str]], schema: dict[str, Any] | None = None,
             model: str | None = None, num_predict: int = 120, num_ctx: int = 1024,
             timeout: float | None = None) -> dict[str, Any] | None:
        model = model or self.default_model()
        # num_ctx is only a hint from the caller: the model keeps its one size
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.ai.get("keepAlive", 0),
            "options": {"temperature": 0, "num_predict": num_predict,
                        "num_ctx": self.context_size(model)},
        }
        if schema is not None:
            payload["format"] = schema
        timeout = float(timeout or self.ai.get("timeoutSeconds", DEFAULT_TIMEOUT))
        with self._lock:
            try:
                resp = self._post(f"{self.host}/api/chat", json=payload, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except Exception:
                return None

    def choose(self, question: str, options: list[str], model: str | None = None) -> str | None:
        if not options:
            return None
        schema = {"type": "object", "properties": {"choice": {"type": "string", "enum": options}},
                  "required": ["choice"]}
        response = self.chat([{"role": "user", "content": question}], schema=schema,
                             model=model or self.agent_model(), num_predict=20,
                             timeout=CHOOSE_TIMEOUT)
        try:
            choice = json.loads(response["message"]["content"]).get("choice")
        except (TypeError, KeyError, ValueError, AttributeError):
            return None
        return choice if choice in options else None

    def ping(self) -> bool:
        try:
            return self._get(f"{self.host}/api/tags", timeout=PING_TIMEOUT).status_code == 200
        except Exception:
            return False

    def warm_up(self, models: list[str] | None = None) -> None:
        """Ask the provider to load each model now (keep_alive from config)."""
        for model in dict.fromkeys(models or [self.default_model(), self.agent_model()]):
            try:
                self._post(f"{self.host}/api/chat", timeout=120.0, json={
                    "model": model, "messages": [], "stream": False,
                    "keep_alive": self.ai.get("keepAlive", 0),
                    "options": {"num_ctx": self.context_size(model)}})  # same size as real calls
            except Exception:
                logger.info("warm-up of %s skipped (provider not reachable)", model)


    def unload(self, models: list[str] | None = None) -> None:
        """Free the model's RAM/VRAM now (chat closed, Arun quitting). It
        loads again by itself on the next request."""
        for model in dict.fromkeys(models or [self.default_model(), self.agent_model()]):
            try:
                self._post(f"{self.host}/api/chat", timeout=10.0, json={
                    "model": model, "messages": [], "stream": False, "keep_alive": 0})
            except Exception:
                logger.info("unload of %s skipped (provider not reachable)", model)


def get_llm(config: dict[str, Any]) -> LLM:
    """The one place the app creates its model client."""
    return LLM(config)
