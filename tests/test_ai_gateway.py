"""AI gateway tests (SKILL §11): no real Ollama — fake/monkeypatched transport."""

from __future__ import annotations

import threading
import time

import pytest

from backend.services.ai_gateway import MAX_TEXT_CHARS, OllamaGateway
from ai.ollama_client import OllamaClient
from backend.db.connection import Database
from backend.db.migrations import migrate
from backend.db.repositories.ai_repo import AiRepo
from backend.main import create_app
from backend.router.router import QuestionRouter
from fastapi.testclient import TestClient

CFG = {
    "siteMatchers": {"youtube.com": ["YouTube"], "instagram.com": ["Instagram"]},
    "distractingSites": ["youtube.com", "instagram.com"],
    "waterDailyTarget": 8,
    "ai": {"enabled": True, "host": "http://localhost:11434",
           "model": "qwen2.5:0.5b", "timeoutSeconds": 15, "keepAlive": 0,
           "logPrompts": False},
}


class FakeClient:
    def __init__(self, content: str | None = None, delay: float = 0.0):
        self.content = content
        self.delay = delay
        self.messages: list | None = None
        self.active = 0
        self.max_active = 0

    def chat(self, messages):
        self.messages = messages
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.delay:
            time.sleep(self.delay)
        self.active -= 1
        if self.content is None:
            return None
        return {"message": {"content": self.content}}


class ExplodingClient:
    def chat(self, messages):
        raise AssertionError("client must not be called")


@pytest.fixture()
def db():
    database = Database(":memory:")
    migrate(database.raw)
    yield database
    database.close()


def gateway(db, client, **ai_overrides):
    cfg = {**CFG, "ai": {**CFG["ai"], **ai_overrides}}
    return OllamaGateway(db, cfg, client=client), cfg


def last_call(db) -> dict:
    rows = AiRepo(db).recent(1)
    assert rows, "expected an ai_calls row"
    row = rows[0]
    return {"intent": row["intent"], "latency_ms": row["latency_ms"],
            "success": row["success"]}


# ---- gateway behaviour ----

def test_valid_json_returns_validated_intent(db):
    gw, _ = gateway(db, FakeClient(
        '{"intent": "screen_time", "period": "yesterday"}'))
    intent = gw.parse_intent("some odd phrasing")
    assert intent == {"intent": "screen_time", "application": None,
                      "period": "yesterday", "comparison": None, "folder": None}
    call = last_call(db)
    assert call["intent"] == "screen_time" and call["success"] == 1
    assert call["latency_ms"] >= 0


def test_invalid_json_logs_failure(db):
    gw, _ = gateway(db, FakeClient("this is { not json"))
    assert gw.parse_intent("zzz") is None
    call = last_call(db)
    assert call["success"] == 0 and call["intent"] is None


def test_valid_json_but_bad_intent_logs_failure(db):
    gw, _ = gateway(db, FakeClient('{"intent": "launch_nuke"}'))
    assert gw.parse_intent("zzz") is None
    assert last_call(db)["success"] == 0


def test_client_timeout_none_logs_failure(db):
    gw, _ = gateway(db, FakeClient(content=None))  # client hit timeout
    assert gw.parse_intent("zzz") is None
    assert last_call(db)["success"] == 0


def test_disabled_returns_none_without_touching_client(db):
    gw, _ = gateway(db, ExplodingClient(), enabled=False)
    assert gw.parse_intent("zzz") is None
    assert AiRepo(db).stats()["calls"] == 0


def test_user_text_truncated_to_300_chars(db):
    client = FakeClient('{"intent": "unknown"}')
    gw, _ = gateway(db, client)
    gw.parse_intent("x" * 500)
    last_message = client.messages[-1]
    assert last_message["role"] == "user"
    assert last_message["content"] == "x" * MAX_TEXT_CHARS


def test_log_prompts_false_stores_null(db):
    gw, _ = gateway(db, FakeClient('{"intent": "unknown"}'))
    gw.parse_intent("my secret question")
    stored = db.query_one("SELECT prompt FROM ai_calls ORDER BY id DESC LIMIT 1")
    assert stored["prompt"] is None


def test_log_prompts_true_stores_user_text(db):
    gw, _ = gateway(db, FakeClient('{"intent": "unknown"}'), logPrompts=True)
    gw.parse_intent("my secret question")
    stored = db.query_one("SELECT prompt FROM ai_calls ORDER BY id DESC LIMIT 1")
    assert stored["prompt"] == "my secret question"


# ---- OllamaClient (monkeypatched transport) ----

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def make_client(post, **ai_overrides):
    cfg = {**CFG, "ai": {**CFG["ai"], **ai_overrides}}
    return OllamaClient(cfg, post=post)


def test_client_builds_correct_payload():
    seen = {}

    def post(url, json=None, timeout=None):
        seen.update(url=url, payload=json, timeout=timeout)
        return FakeResponse({"message": {"content": "{}"}})

    client = make_client(post)
    assert client.chat([{"role": "user", "content": "hi"}]) == \
        {"message": {"content": "{}"}}
    assert seen["url"] == "http://localhost:11434/api/chat"
    assert seen["timeout"] == 15.0
    payload = seen["payload"]
    assert payload["stream"] is False
    schema = payload["format"]  # structured outputs: constrained JSON
    assert schema["required"] == ["intent"]
    assert "launch_nuke" not in schema["properties"]["intent"]["enum"]
    assert schema["properties"]["target"]["type"] == ["string", "null"]
    assert payload["keep_alive"] == 0
    assert payload["model"] == "qwen2.5:0.5b"
    assert payload["options"] == {"temperature": 0, "num_predict": 120,
                                  "num_ctx": 1024}


def test_client_swallows_timeout_and_connection_errors():
    def timeout_post(*a, **k):
        raise TimeoutError("read timed out")

    def conn_post(*a, **k):
        raise ConnectionError("refused")

    assert make_client(timeout_post).chat([]) is None
    assert make_client(conn_post).chat([]) is None


def test_client_single_flight_serialises_calls():
    active, max_active = 0, 0
    guard = threading.Lock()

    def counting_post(*a, **k):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.15)
        with guard:
            active -= 1
        return FakeResponse({"message": {"content": "{}"}})

    client = make_client(counting_post)
    threads = [threading.Thread(target=lambda: client.chat([]))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max_active == 1  # second caller waited for the first


# ---- integration with QuestionRouter + lifespan wiring ----

def test_router_fallback_executes_gateway_intent(db):
    gw, cfg = gateway(db, FakeClient('{"intent": "screen_time"}'))
    router = QuestionRouter(db, cfg, ai_gateway=gw)
    resp = router.ask("zzz unrecognisable zzz")
    assert "screen time" in resp["text"]
    assert last_call(db)["success"] == 1


def test_lifespan_creates_gateway_when_enabled(cfg):
    app = create_app(cfg, start_services=False)
    with TestClient(app):
        assert isinstance(app.state.ai_gateway, OllamaGateway)


def test_lifespan_gateway_none_when_disabled(cfg):
    cfg["ai"]["enabled"] = False
    app = create_app(cfg, start_services=False)
    with TestClient(app):
        assert app.state.ai_gateway is None
