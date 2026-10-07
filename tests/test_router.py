"""QuestionRouter tests: rules → execute, AI fallback, pending confirmations."""

from __future__ import annotations

from datetime import date

import pytest

from backend.db.connection import Database
from backend.db.migrations import migrate
from backend.db.repositories.usage_repo import UsageRepo
from backend.db.repositories.water_repo import WaterRepo
from backend.router.confirmations import PendingConfirmation
from backend.router.router import CLARIFICATION, QuestionRouter

CFG = {
    "siteMatchers": {"youtube.com": ["YouTube", "yt"],
                     "instagram.com": ["Instagram"]},
    "distractingSites": ["youtube.com", "instagram.com"],
    "waterDailyTarget": 8,
    "browsers": ["chrome.exe"],
}


class FakeGateway:
    def __init__(self, result):
        self.result = result
        self.calls: list[str] = []

    def parse_intent(self, text: str):
        self.calls.append(text)
        return self.result


class FakeTidy:
    def __init__(self):
        self.propose_calls: list[str] = []
        self.confirm_calls: list[str] = []
        self.undo_calls = 0

    def propose(self, folder: str) -> dict:
        self.propose_calls.append(folder)
        return {"proposal_id": "p1", "text": f"Move 5 files from {folder}?",
                "animation": "idle", "needs_confirmation": True}

    def confirm(self, proposal_id: str) -> dict:
        self.confirm_calls.append(proposal_id)
        return {"text": "Done — 5 files moved.", "animation": "happy"}

    def undo(self) -> dict:
        self.undo_calls += 1
        return {"text": "Moved them back.", "animation": "smile"}


@pytest.fixture()
def db():
    database = Database(":memory:")
    migrate(database.raw)
    repo = UsageRepo(database)
    today = date.today().isoformat()
    repo.insert_session("Chrome", f"{today}T09:00:00+05:30",
                        f"{today}T11:00:00+05:30", 7200, today,
                        website="youtube.com")
    yield database
    database.close()


@pytest.fixture()
def router(db):
    return QuestionRouter(db, CFG)


# ---- rules execute without AI ----

def test_rule_hit_executes_without_ai(router):
    resp = router.ask("how much youtube did i use today")
    assert "YouTube" in resp["text"] and "2h" in resp["text"]
    assert resp["animation"] == "warn"  # 2h >= warn threshold
    assert resp["needs_confirmation"] is False


def test_top_app_rule(router):
    resp = router.ask("what app did I use the most today")
    assert "Chrome" in resp["text"]


def test_log_water_writes_row(router, db):
    resp = router.ask("I drank a glass")
    assert "1 of 8" in resp["text"]
    assert WaterRepo(db).count_drunk(date.today().isoformat()) == 1


def test_tidy_without_service_gives_graceful_text(router):
    resp = router.ask("organize my downloads")
    assert "isn't ready" in resp["text"]
    assert resp["needs_confirmation"] is False


# ---- clarification / AI fallback ----

def test_unknown_text_without_ai_clarifies(router):
    resp = router.ask("tell me a joke")
    assert resp["text"] == CLARIFICATION
    assert resp["animation"] == "idle"


def test_fallback_calls_gateway_and_executes(db):
    gw = FakeGateway({"intent": "screen_time", "period": "yesterday",
                      "application": None, "comparison": None, "folder": None})
    router = QuestionRouter(db, CFG, ai_gateway=gw)
    resp = router.ask("zzz gibberish zzz")
    assert gw.calls == ["zzz gibberish zzz"]
    assert "screen time" in resp["text"]


def test_gateway_not_called_when_rules_hit(db):
    gw = FakeGateway({"intent": "screen_time"})
    router = QuestionRouter(db, CFG, ai_gateway=gw)
    router.ask("how much youtube did i use today")
    assert gw.calls == []


def test_invalid_gateway_output_clarifies(db):
    for bad in [{"intent": "launch_nuke"},
                {"intent": "unknown"},
                {"intent": "usage_query", "application": "github.com"},
                {"intent": "usage_query", "application": "youtube.com",
                 "period": "fortnight"},
                {"intent": "tidy_folder", "folder": "hacked"},
                None, "just a string"]:
        gw = FakeGateway(bad)
        router = QuestionRouter(db, CFG, ai_gateway=gw)
        assert router.ask("zzz")["text"] == CLARIFICATION, bad


# ---- pending confirmation ----

def test_yes_executes_pending_tidy(db):
    fake = FakeTidy()
    router = QuestionRouter(db, CFG, tidy_service=fake)
    router.ask("organize my downloads")
    assert fake.propose_calls == ["downloads"]
    resp = router.ask("yes")
    assert resp["text"] == "Done — 5 files moved."
    assert fake.confirm_calls == ["p1"]
    assert router.pending.get() is None  # cleared after answering


def test_no_cancels_pending(db):
    fake = FakeTidy()
    router = QuestionRouter(db, CFG, tidy_service=fake)
    router.ask("tidy up my desktop")
    resp = router.ask("no")
    assert "cancelled" in resp["text"]
    assert fake.confirm_calls == []
    assert router.pending.get() is None


def test_pending_expires_after_two_minutes(db):
    now = [1_000_000.0]
    fake = FakeTidy()
    router = QuestionRouter(db, CFG, tidy_service=fake, clock=lambda: now[0])
    router.ask("organize my documents")
    now[0] += 119
    assert router.ask("yes")["text"] == "Done — 5 files moved."  # still valid
    assert fake.confirm_calls == ["p1"]

    router.ask("organize my documents")  # pending again
    now[0] += 121
    resp = router.ask("yes")
    assert resp["text"] == CLARIFICATION  # expired -> no confirmation left
    assert fake.confirm_calls == ["p1"]  # not called a second time
    assert router.pending.get() is None


def test_yes_without_pending_is_not_a_confirmation(router):
    resp = router.ask("yes")
    assert resp["text"] == CLARIFICATION


def test_undo_tidy_without_service(router):
    resp = router.ask("undo that")
    assert "isn't ready" in resp["text"]


# ---- open / close a tracked site ----

class FakeOSAdapter:
    def __init__(self, fg=None, dnd=False):
        self.fg = fg
        self.dnd = dnd
        self.closed = False

    def get_foreground_window(self):
        return self.fg

    def is_dnd_active(self):
        return self.dnd

    def send_close_tab(self):
        self.closed = True
        return True


def test_open_site_launches_browser(db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "backend.services.app_launcher_service.AppLauncherService.open_site",
        lambda self, site: calls.append(site) or True,
    )
    router = QuestionRouter(db, CFG)
    resp = router.ask("open youtube")
    assert calls == ["youtube.com"]
    assert "Opening" in resp["text"] and "YouTube" in resp["text"]
    assert resp["animation"] == "working"


def test_close_site_tab_closes_when_foreground_matches(db):
    adapter = FakeOSAdapter(fg={"process_name": "chrome.exe", "title": "YouTube - Chrome"})
    router = QuestionRouter(db, CFG, os_adapter=adapter)
    resp = router.ask("close the youtube tab")
    assert adapter.closed is True
    assert "Closed" in resp["text"]
    assert resp["animation"] == "happy"


def test_close_site_tab_refuses_when_foreground_is_different(db):
    adapter = FakeOSAdapter(fg={"process_name": "chrome.exe", "title": "Instagram - Chrome"})
    router = QuestionRouter(db, CFG, os_adapter=adapter)
    resp = router.ask("close the youtube tab")
    assert adapter.closed is False
    assert "don't see" in resp["text"]


def test_close_site_tab_without_adapter(router):
    resp = router.ask("close the youtube tab")
    assert "Couldn't close" in resp["text"]


# ---- HTTP endpoint ----

def test_post_ask_endpoint(client):
    resp = client.post("/ask", json={"text": "how much screen time today"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"text", "animation", "needs_confirmation",
                         "proposal_id", "data"}
    assert "screen time" in body["text"]


def test_post_ask_endpoint_garbage(client):
    body = client.post("/ask", json={"text": "asdfghjkl"}).json()
    assert body["text"] == CLARIFICATION


def test_post_ask_empty_text_is_validation_error(client):
    assert client.post("/ask", json={"text": ""}).status_code == 422
