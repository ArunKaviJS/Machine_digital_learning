"""Unused-app reminder: ask once after N unused minutes, close only on yes."""

from __future__ import annotations

import asyncio

import pytest

from backend.scheduler.idle_app_loop import IdleAppLoop
from backend.services.idle_app_service import PENDING_TTL_SECONDS, IdleAppService
from tests.fakes import FakeOSAdapter, fg

CFG = {"idleAppMinutes": 30, "idleAppIgnore": ["ollama app.exe"],
       "idleThresholdSeconds": 120}
MIN = 60.0


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def win(hwnd, process, title):
    return {"hwnd": hwnd, "pid": hwnd, "process_name": process, "title": title}


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def os_fake():
    fake = FakeOSAdapter(foreground=fg("Code.exe", "main.py - VS Code"))
    fake.windows = [win(1, "Code.exe", "main.py - VS Code"),
                    win(2, "WhatsApp.Root.exe", "WhatsApp"),
                    win(3, "ollama app.exe", "Ollama")]
    return fake


@pytest.fixture()
def svc(os_fake, clock):
    return IdleAppService(CFG, os_fake, clock=clock)


def test_no_question_before_threshold(svc, clock):
    svc.tick()
    clock.advance(29 * MIN)
    assert svc.tick() == []


def test_asks_about_unused_app_after_threshold(svc, clock):
    svc.tick()
    clock.advance(31 * MIN)
    events = svc.tick()
    assert events == [{"type": "idle_app", "key": "proc:whatsapp.root",
                       "name": "WhatsApp", "minutes": 31}]


def test_foreground_app_and_ignored_apps_are_never_asked(svc, clock):
    svc.tick()
    clock.advance(31 * MIN)
    names = [e["name"] for e in svc.tick() if e["type"] == "idle_app"]
    assert "Code" not in names and "Ollama" not in names


def test_only_one_question_at_a_time(svc, os_fake, clock):
    os_fake.windows.append(win(4, "Notepad.exe", "notes.txt - Notepad"))
    svc.tick()
    clock.advance(31 * MIN)
    assert len([e for e in svc.tick() if e["type"] == "idle_app"]) == 1
    clock.advance(5 * MIN)
    assert [e for e in svc.tick() if e["type"] == "idle_app"] == []  # still pending


def test_yes_closes_every_window_of_that_app(svc, os_fake, clock):
    os_fake.windows.append(win(5, "WhatsApp.Root.exe", "WhatsApp call"))
    svc.tick()
    clock.advance(31 * MIN)
    key = svc.tick()[0]["key"]
    result = svc.answer(key, close=True)
    assert result["text"].startswith("Closing WhatsApp")
    assert sorted(os_fake.closed) == [2, 5]


def test_keep_it_means_never_ask_again_while_open(svc, os_fake, clock):
    svc.tick()
    clock.advance(31 * MIN)
    key = svc.tick()[0]["key"]
    assert "leave WhatsApp open" in svc.answer(key, close=False)["text"]
    assert os_fake.closed == []
    clock.advance(120 * MIN)
    assert [e for e in svc.tick() if e["type"] == "idle_app"] == []


def test_using_the_app_again_clears_the_question(svc, os_fake, clock):
    svc.tick()
    clock.advance(31 * MIN)
    key = svc.tick()[0]["key"]
    os_fake.foreground = fg("WhatsApp.Root.exe", "WhatsApp")
    assert {"type": "idle_app_cleared", "key": key} in svc.tick()


def test_no_questions_while_user_is_away_or_dnd(svc, os_fake, clock):
    svc.tick()
    clock.advance(31 * MIN)
    os_fake.idle_seconds = 600
    assert svc.tick() == []
    os_fake.idle_seconds = 0
    os_fake.dnd = True
    assert svc.tick() == []


def test_unanswered_question_expires_as_keep(svc, clock):
    svc.tick()
    clock.advance(31 * MIN)
    key = svc.tick()[0]["key"]
    clock.advance(PENDING_TTL_SECONDS + 1)
    assert {"type": "idle_app_cleared", "key": key} in svc.tick()
    clock.advance(60 * MIN)
    assert all(e.get("key") != key for e in svc.tick() if e["type"] == "idle_app")


def test_closing_the_app_yourself_forgets_it(svc, os_fake, clock):
    svc.tick()
    clock.advance(31 * MIN)
    key = svc.tick()[0]["key"]
    os_fake.windows = [w for w in os_fake.windows if w["hwnd"] != 2]
    assert {"type": "idle_app_cleared", "key": key} in svc.tick()
    assert svc.answer(key, close=True)["text"] == "That app is already closed, bro."


def test_loop_broadcasts_events(svc, clock):
    class Notifications:
        def __init__(self):
            self.sent = []

        async def broadcast(self, payload):
            self.sent.append(payload)

    notifications = Notifications()
    loop = IdleAppLoop(svc, notifications)
    asyncio.run(loop.step())
    clock.advance(31 * MIN)
    asyncio.run(loop.step())
    assert notifications.sent[0]["type"] == "idle_app"


def test_answer_endpoint(client):
    r = client.post("/apps/idle/answer", json={"key": "proc:nothing", "close": True})
    assert r.status_code == 200
    assert r.json() == {"text": "That app is already closed, bro.", "animation": "smile"}


def test_answer_endpoint_requires_token(cfg):
    from fastapi.testclient import TestClient

    from backend.main import create_app
    with TestClient(create_app(cfg, start_services=False)) as c:
        assert c.post("/apps/idle/answer", json={"key": "x", "close": True}).status_code == 401
