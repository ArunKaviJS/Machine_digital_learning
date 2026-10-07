"""GuardService state-machine tests (SKILL §15) with fake adapter + clock."""

from __future__ import annotations

import os
from datetime import datetime

import pytest

from backend.db.connection import Database
from backend.db.migrations import migrate
from backend.services.guard_service import GuardService
from tests.fakes import FakeOSAdapter, fg

CFG = {
    "browsers": ["chrome.exe", "msedge.exe"],
    "siteMatchers": {"youtube.com": ["YouTube"]},
    "dndApps": ["zoom.exe", "teams.exe"],
    "idleThresholdSeconds": 120,
    "maxGapSeconds": 120,
    "pollSeconds": 2,
    "nagAfterMinutes": 15,      # 900 s
    "closeAfterMinutes": 25,    # 1500 s  (+ warning 60 -> close at 1560)
    "warningSeconds": 60,
    "nagRepeatSeconds": 120,
    "breakResetMinutes": 10,    # 600 s
    "demoMode": False,
}

T0 = datetime(2026, 10, 7, 10, 0, 0).timestamp()
YT = fg("chrome.exe", "Funny Cats - YouTube")
CODE = fg("Code.exe", "main.py - Visual Studio Code")
ZOOM = fg("zoom.exe", "Weekly Sync - Zoom")


class FakeClock:
    def __init__(self, start: float = T0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


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
def adapter():
    return FakeOSAdapter(foreground=YT)


def make(db, adapter, clock, **cfg_overrides):
    cfg = {**CFG, **cfg_overrides}
    return GuardService(db, cfg, adapter, clock=clock)


def tick_in(guard, clock, seconds, step=10):
    """Advance the clock in small steps, ticking each step."""
    events = []
    remaining = seconds
    while remaining > 0:
        s = min(step, remaining)
        clock.advance(s)
        events.extend(guard.tick())
        remaining -= s
    return events


def event_types(events):
    return [e["type"] for e in events]


def event_rows(db):
    return [r["type"] for r in db.query("SELECT type FROM guard_events ORDER BY id")]


# ---- streak ----

def test_streak_builds_while_on_site(db, clock, adapter):
    guard = make(db, adapter, clock)
    assert guard.tick() == []                    # first tick, no accrual
    assert guard.state == "TRACKING"
    tick_in(guard, clock, 600)
    assert guard.streak == 600
    assert guard.state == "TRACKING"
    assert guard.repo.get_streak() == 600        # persisted


def test_self_window_is_ignored(db, clock, adapter):
    adapter.foreground = fg("arun.exe", "Arun", pid=os.getpid())
    guard = make(db, adapter, clock)
    guard.tick()
    tick_in(guard, clock, 300)
    assert guard.streak == 0
    assert guard.tick() == []


def test_away_break_resets_streak(db, clock, adapter):
    guard = make(db, adapter, clock)
    guard.tick()
    tick_in(guard, clock, 500)
    assert guard.streak == 500
    adapter.foreground = CODE
    tick_in(guard, clock, 600, step=60)
    assert guard.streak == 0
    assert guard.state == "IDLE"


# ---- nagging ----

def test_nag_fires_at_threshold_and_repeats_on_schedule(db, clock, adapter):
    guard = make(db, adapter, clock)
    guard.tick()
    assert event_types(tick_in(guard, clock, 899)) == []
    nag_events = event_types(tick_in(guard, clock, 1))
    assert nag_events == ["nag"]
    assert guard.state == "NAGGING"
    # no repeat before nagRepeatSeconds (120)
    assert event_types(guard.tick()) == []
    assert event_types(tick_in(guard, clock, 119)) == []
    # fires once the gap is reached
    repeat = event_types(tick_in(guard, clock, 1))
    assert repeat == ["nag"]
    assert event_rows(db).count("nag") == 2


def test_nag_suppressed_while_dnd(db, clock, adapter):
    adapter.dnd = True
    guard = make(db, adapter, clock)
    guard.tick()
    assert tick_in(guard, clock, 1000) == []     # streak built, no nag
    assert guard.streak >= 900
    adapter.dnd = False
    assert event_types(tick_in(guard, clock, 1)) == ["nag"]


def test_nag_paused_while_meeting_app_foreground(db, clock, adapter):
    guard = make(db, adapter, clock)
    guard.tick()
    tick_in(guard, clock, 1000)
    assert guard.state == "NAGGING"
    adapter.foreground = ZOOM
    assert tick_in(guard, clock, 300) == []      # paused, no nags
    assert guard.state == "TRACKING"


# ---- countdown + close ----

def test_countdown_ticks_then_closes_with_safety_recheck(db, clock, adapter):
    guard = make(db, adapter, clock)
    guard.tick()
    start = event_types(tick_in(guard, clock, 1500))
    assert "countdown_start" in start
    assert guard.state == "COUNTDOWN"
    # countdown ticks with decreasing seconds_left (59 at t+1 ... 50 at t+10)
    events = tick_in(guard, clock, 10, step=1)
    ticks = [e for e in events if e["type"] == "countdown_tick"]
    assert ticks and ticks[0]["seconds_left"] == 59
    assert ticks[-1]["seconds_left"] == 50
    # finish the 60 s window -> safety re-read still YouTube -> close
    closing = event_types(tick_in(guard, clock, 50, step=1))
    assert closing[-1] == "tab_closed"
    assert adapter.close_tab_calls == 1
    assert guard.state == "COOLDOWN"
    assert guard.streak == 0
    rows = event_rows(db)
    assert "countdown_start" in rows and "tab_closed" in rows


def test_close_cancelled_when_foreground_changed(db, clock, adapter):
    guard = make(db, adapter, clock)
    guard.tick()
    tick_in(guard, clock, 1500)
    tick_in(guard, clock, 1)                     # enter COUNTDOWN
    assert guard.state == "COUNTDOWN"
    adapter.foreground = CODE                    # user switched away
    closing = event_types(tick_in(guard, clock, 60, step=10))
    assert "cancelled" in closing and "tab_closed" not in closing
    assert adapter.close_tab_calls == 0
    assert guard.state == "COOLDOWN"


def test_close_cancelled_when_dnd_turns_on_mid_countdown(db, clock, adapter):
    guard = make(db, adapter, clock)
    guard.tick()
    tick_in(guard, clock, 1500)
    tick_in(guard, clock, 1)
    adapter.dnd = True
    closing = event_types(tick_in(guard, clock, 60, step=10))
    assert "cancelled" in closing
    assert adapter.close_tab_calls == 0


def test_cooldown_expires_to_idle(db, clock, adapter):
    guard = make(db, adapter, clock)
    guard.tick()
    tick_in(guard, clock, 1560, step=10)         # through close
    assert guard.state == "COOLDOWN"
    adapter.foreground = CODE                    # user left the site
    tick_in(guard, clock, 600, step=60)          # break reset window
    assert guard.state == "IDLE"


def test_snooze_from_countdown_pauses_machine(db, clock, adapter):
    guard = make(db, adapter, clock)
    guard.tick()
    tick_in(guard, clock, 1500)
    tick_in(guard, clock, 1)
    payload = guard.snooze(300)
    assert payload["type"] == "snoozed"
    assert guard.state == "COOLDOWN"
    assert guard.streak == 0
    assert event_types(tick_in(guard, clock, 299)) == []
    assert adapter.close_tab_calls == 0
    assert "snoozed" in event_rows(db)
    tick_in(guard, clock, 1)                     # cooldown over
    assert guard.state == "IDLE"


# ---- idle / demo ----

def test_idle_treated_as_away_and_suppresses(db, clock, adapter):
    adapter.idle_seconds = 200
    guard = make(db, adapter, clock)
    guard.tick()
    assert tick_in(guard, clock, 1000) == []     # no nag while idle
    assert guard.streak == 0                     # streak not accruing


def test_demo_mode_timings(db, clock, adapter):
    guard = make(db, adapter, clock, demoMode=True)
    guard.tick()
    # nag at 10 s
    assert event_types(tick_in(guard, clock, 10, step=1)) == ["nag"]
    # countdown starts at 20 s
    events = tick_in(guard, clock, 10, step=1)
    assert "countdown_start" in event_types(events)
    assert guard.state == "COUNTDOWN"
    # close at 30 s (20 + warning 10)
    events = tick_in(guard, clock, 10, step=1)
    assert "tab_closed" in event_types(events)
    assert adapter.close_tab_calls == 1
    assert guard.state == "COOLDOWN"


def test_pause_and_resume_silences_guard_and_water(db, clock, adapter):
    from backend.services.water_service import WaterService

    guard = make(db, adapter, clock)
    water = WaterService(db, CFG, clock=clock)

    assert not guard.is_paused()
    assert not water.blocked(adapter)

    # Manual pause
    res = guard.pause()
    assert res["paused"] is True
    assert guard.is_paused()
    assert water.blocked(adapter)

    # Ticks with YouTube foreground should not accrue streak or nag
    guard.tick()
    events = tick_in(guard, clock, 1200, step=10)
    assert events == []
    assert guard.streak == 0

    # Resume
    res_resume = guard.resume()
    assert res_resume["paused"] is False
    assert not guard.is_paused()
    assert not water.blocked(adapter)


def test_cancel_countdown(db, clock, adapter):
    guard = make(db, adapter, clock)
    guard.tick()
    tick_in(guard, clock, 1500)
    tick_in(guard, clock, 1)
    assert guard.state == "COUNTDOWN"
    assert guard.get_status()["seconds_left"] > 0

    res = guard.cancel()
    assert res["type"] == "cancelled"
    assert guard.state == "IDLE"
    assert guard.streak == 0
    assert guard.get_status()["seconds_left"] == 0
    assert "cancelled" in event_rows(db)


def test_safety_check_never_closes_arun_window(db, clock, adapter):
    import os
    guard = make(db, adapter, clock)
    guard.tick()
    tick_in(guard, clock, 1500)
    tick_in(guard, clock, 1)
    assert guard.state == "COUNTDOWN"

    # Set foreground to Arun window at expiry
    arun_window = {"hwnd": 999, "pid": os.getpid(), "process_name": "python.exe", "title": "Arun"}
    adapter.foreground = arun_window
    closing = event_types(tick_in(guard, clock, 60, step=10))
    assert "cancelled" in closing
    assert adapter.close_tab_calls == 0


# ---- Guard API endpoints ----

def test_api_guard_status_and_pause_resume(client):
    r = client.get("/guard/status")
    assert r.status_code == 200
    body = r.json()
    assert "state" in body and "paused" in body and "streak_seconds" in body

    # Pause
    r_pause = client.post("/pause")
    assert r_pause.status_code == 200
    assert r_pause.json()["paused"] is True

    # Status reflects paused
    assert client.get("/guard/status").json()["paused"] is True

    # Resume
    r_resume = client.post("/resume")
    assert r_resume.status_code == 200
    assert r_resume.json()["paused"] is False
    assert client.get("/guard/status").json()["paused"] is False


def test_api_guard_cancel_and_snooze(client):
    r_cancel = client.post("/guard/cancel")
    assert r_cancel.status_code == 200
    assert r_cancel.json()["status"]["state"] == "IDLE"

    r_snooze = client.post("/guard/snooze")
    assert r_snooze.status_code == 200
    assert "until" in r_snooze.json()

