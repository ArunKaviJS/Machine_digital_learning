"""WaterService + WaterLoop + water/WS endpoint tests (SKILL §16/§18)."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from backend.db.connection import Database
from backend.db.migrations import migrate
from backend.db.repositories.water_repo import WaterRepo
from backend.scheduler.water_loop import WaterLoop
from backend.services.water_service import WaterService
from backend.ws.notifications import NotificationManager
from tests.fakes import FakeOSAdapter

CFG = {"waterIntervalMinutes": 60, "waterDailyTarget": 8,
       "waterSnoozeMinutes": 10, "idleThresholdSeconds": 120}

T0 = datetime(2026, 10, 7, 10, 0, 0).timestamp()  # 10:00 local


class FakeClock:
    def __init__(self, start: float = T0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeNotifications:
    def __init__(self):
        self.payloads: list[dict] = []

    async def broadcast(self, payload: dict) -> int:
        self.payloads.append(payload)
        return 1


@pytest.fixture()
def db():
    database = Database(":memory:")
    migrate(database.raw)
    yield database
    database.close()


@pytest.fixture()
def clock():
    return FakeClock()


@pytest.fixture()
def service(db, clock):
    return WaterService(db, CFG, clock=clock)


# ---- timing ----

def test_first_run_due_after_one_interval(service, clock):
    assert service.next_due() == T0 + 3600
    assert service.due() is False
    clock.advance(3600)
    assert service.due() is True


def test_reminder_resets_cadence(service, clock):
    clock.advance(3600)
    service.mark_reminder_shown()
    assert service.due() is False
    clock.advance(3599)
    assert service.due() is False
    clock.advance(1)
    assert service.due() is True


def test_drank_resets_cadence_and_counts(service, clock):
    clock.advance(3600)
    result = service.drank()
    assert result == {"count": 1, "target": 8}
    assert service.today_count() == 1
    clock.advance(3599)
    assert service.due() is False
    clock.advance(1)
    assert service.due() is True


def test_snooze_buys_ten_minutes(service, clock):
    clock.advance(3600)
    service.snooze()
    assert service.next_due() == T0 + 3600 + 600
    clock.advance(599)
    assert service.due() is False
    clock.advance(1)
    assert service.due() is True


def test_blocked_by_dnd_or_idle(service):
    assert service.blocked(FakeOSAdapter(dnd=True)) is True
    assert service.blocked(FakeOSAdapter(idle_seconds=200)) is True
    assert service.blocked(FakeOSAdapter(dnd=False, idle_seconds=5)) is False


def test_last_reminder_and_summary(service, clock):
    assert service.last_reminder() is None
    clock.advance(3600)
    service.mark_reminder_shown()
    row = service.last_reminder()
    assert row["type"] == "reminder_shown"
    summary = service.today_summary()
    assert summary["count"] == 0 and summary["target"] == 8
    assert summary["next_due"]  # ISO timestamp


# ---- scheduler loop ----

def make_loop(service, adapter=None):
    return WaterLoop(service, FakeNotifications(), adapter)


def test_step_not_due_then_fires_once(service, clock):
    loop = make_loop(service)
    assert asyncio.run(loop.step()) == "not_due"
    clock.advance(3600)
    assert asyncio.run(loop.step()) == "fired"
    assert loop.notifications.payloads == [
        {"type": "water_due", "count": 0, "target": 8}]
    # reminder logged -> not due again
    assert asyncio.run(loop.step()) == "not_due"


def test_step_blocked_adapter_skips_fire(service, clock):
    loop = make_loop(service, FakeOSAdapter(dnd=True))
    clock.advance(3600)
    assert asyncio.run(loop.step()) == "blocked"
    assert WaterRepo(service.repo.db).last_of_type("reminder_shown") is None
    assert loop.notifications.payloads == []
    # DND clears -> next tick fires
    loop.os_adapter = FakeOSAdapter(dnd=False)
    assert asyncio.run(loop.step()) == "fired"


def test_notification_manager_broadcast_and_dead_socket_drop():
    manager = NotificationManager()

    class FakeWS:
        def __init__(self, dead=False):
            self.dead = dead
            self.sent = []

        async def send_json(self, payload):
            if self.dead:
                raise RuntimeError("socket closed")
            self.sent.append(payload)

    alive, dead = FakeWS(), FakeWS(dead=True)
    manager.connect(alive)
    manager.connect(dead)
    sent = asyncio.run(manager.broadcast({"type": "water_due"}))
    assert sent == 1
    assert alive.sent == [{"type": "water_due"}]
    assert manager.client_count == 1  # dead socket dropped


# ---- HTTP endpoints ----

def test_water_drink_endpoint(client):
    body = client.post("/water/drink").json()
    assert body["count"] == 1
    assert body["target"] == 8
    assert body["animation"] == "happy"


def test_water_today_endpoint(client):
    client.post("/water/drink")
    body = client.get("/water/today").json()
    assert body["count"] == 1
    assert body["target"] == 8
    assert "T" in body["next_due"]  # ISO


def test_water_snooze_endpoint(client):
    body = client.post("/water/snooze").json()
    assert body["snoozed"] is True
    assert "T" in body["next_due"]


def test_water_endpoints_feed_quick_question(client):
    client.post("/water/drink")
    client.post("/water/drink")
    body = client.post("/ask/quick",
                       json={"question_id": "water_today"}).json()
    assert "2 of 8" in body["text"]


def test_ws_endpoint_registers_and_unregisters_client(client):
    assert client.app.state.notifications.client_count == 0
    token = client.app.state.api_token
    with client.websocket_connect(f"/ws/events?token={token}"):
        assert client.app.state.notifications.client_count == 1
    assert client.app.state.notifications.client_count == 0
