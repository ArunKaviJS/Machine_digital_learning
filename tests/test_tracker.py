"""Tests for ActivityTracker: simulated ticks with a fake clock + FakeOSAdapter."""

from __future__ import annotations

import os
from datetime import datetime

from backend.db.connection import Database, get_meta
from backend.db.migrations import migrate
from backend.tracker.activity_tracker import (
    HEARTBEAT_KEY,
    OPEN_SESSION_KEY,
    ActivityTracker,
)
from tests.fakes import FakeOSAdapter, fg

YOUTUBE = "my video - YouTube - Google Chrome"
DAY1 = datetime(2026, 10, 7, 10, 0, 0).timestamp()      # 10:00 local
MIDNIGHT_EVE = datetime(2026, 10, 7, 23, 59, 0).timestamp()


class Clock:
    def __init__(self, t: float):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def make(cfg: dict, foreground, clock: Clock):
    db = Database(":memory:")
    migrate(db.raw)
    osa = FakeOSAdapter(foreground=foreground)
    tracker = ActivityTracker(db, osa, cfg, clock=clock)
    return tracker, db, osa


def rows(db: Database) -> list[dict]:
    return [dict(r) for r in db.query("SELECT * FROM usage_sessions ORDER BY id")]


def test_session_opens_extends_and_closes(cfg):
    clock = Clock(DAY1)
    tracker, db, osa = make(cfg, fg("chrome.exe", YOUTUBE), clock)
    tracker.tick()
    assert rows(db) == []                      # still open, nothing written yet

    clock.advance(10)
    tracker.tick()
    assert rows(db) == []                      # same (app, site) -> extend

    osa.foreground = fg("Code.exe", "main.py - Code")
    tracker.tick()
    saved = rows(db)
    assert len(saved) == 1
    assert saved[0]["application"] == "Chrome"
    assert saved[0]["website"] == "youtube.com"
    assert saved[0]["duration_seconds"] == 10
    assert saved[0]["date"] == "2026-10-07"

    clock.advance(5)
    tracker.tick()
    tracker.close()
    saved = rows(db)
    assert len(saved) == 2
    assert saved[1]["application"] == "Code"
    assert saved[1]["website"] is None
    assert saved[1]["duration_seconds"] == 5
    db.close()


def test_idle_closes_session_at_last_input(cfg):
    clock = Clock(DAY1)
    tracker, db, osa = make(cfg, fg("chrome.exe", YOUTUBE), clock)
    tracker.tick()                             # opens at t0 (idle 0)
    clock.advance(10)
    osa.idle_seconds = 5                       # last input was 5 s ago
    tracker.tick()                             # under threshold -> extend
    clock.advance(125)
    osa.idle_seconds = 130                     # >= 120 -> away
    tracker.tick()
    saved = rows(db)
    assert len(saved) == 1
    assert saved[0]["duration_seconds"] == 5   # ends at last input, not "now"
    assert tracker._open is None
    db.close()


def test_arun_window_is_ignored(cfg):
    clock = Clock(DAY1)
    tracker, db, osa = make(cfg, fg("chrome.exe", YOUTUBE), clock)
    tracker.tick()
    clock.advance(20)
    osa.foreground = fg("python.exe", "Arun", pid=os.getpid())  # user pokes Arun
    tracker.tick()
    clock.advance(10)
    osa.foreground = fg("chrome.exe", YOUTUBE)
    tracker.tick()
    tracker.close()
    saved = rows(db)
    assert len(saved) == 1
    assert saved[0]["website"] == "youtube.com"
    assert saved[0]["duration_seconds"] == 30  # session never broken
    db.close()


def test_midnight_split_produces_two_rows(cfg):
    clock = Clock(MIDNIGHT_EVE)
    tracker, db, osa = make(cfg, fg("chrome.exe", YOUTUBE), clock)
    tracker.tick()
    clock.advance(60)                          # now 00:00 next day
    tracker.tick()
    clock.advance(60)                          # 00:01
    tracker.close()
    saved = rows(db)
    assert [r["date"] for r in saved] == ["2026-10-07", "2026-10-08"]
    assert [r["duration_seconds"] for r in saved] == [60, 60]
    db.close()


def test_gap_is_clamped_never_counted(cfg):
    clock = Clock(DAY1)
    tracker, db, osa = make(cfg, fg("chrome.exe", YOUTUBE), clock)
    tracker.tick()
    clock.advance(10)
    tracker.tick()                             # extend to t0+10
    clock.advance(300)                         # system sleep > maxGapSeconds
    tracker.tick()                             # old session closed at pre-sleep
    clock.advance(10)
    tracker.tick()
    tracker.close()
    saved = rows(db)
    assert len(saved) == 2
    assert [r["duration_seconds"] for r in saved] == [10, 10]  # 300 s gap lost
    db.close()


def test_track_all_apps_false_records_only_sites(cfg):
    cfg = dict(cfg)
    cfg["trackAllApps"] = False
    clock = Clock(DAY1)
    tracker, db, osa = make(cfg, fg("Spotify.exe", "Spotify"), clock)
    tracker.tick()
    clock.advance(5)
    tracker.tick()
    tracker.close()
    assert rows(db) == []                      # untracked app ignored

    osa.foreground = fg("msedge.exe", YOUTUBE)
    tracker.tick()
    clock.advance(7)
    tracker.tick()
    tracker.close()
    saved = rows(db)
    assert len(saved) == 1 and saved[0]["website"] == "youtube.com"
    db.close()


def test_store_titles_flag(cfg):
    cfg = dict(cfg)
    cfg["storeTitles"] = True
    clock = Clock(DAY1)
    tracker, db, osa = make(cfg, fg("chrome.exe", YOUTUBE), clock)
    tracker.tick()
    clock.advance(3)
    tracker.tick()
    tracker.close()
    assert rows(db)[0]["window_title"] == YOUTUBE
    db.close()

    cfg2 = dict(cfg)
    cfg2["storeTitles"] = False
    clock2 = Clock(DAY1)
    tracker2, db2, _ = make(cfg2, fg("chrome.exe", YOUTUBE), clock2)
    tracker2.tick()
    clock2.advance(3)
    tracker2.tick()
    tracker2.close()
    assert rows(db2)[0]["window_title"] is None
    db2.close()


def test_heartbeat_and_crash_recovery(cfg):
    clock = Clock(DAY1)
    tracker, db, osa = make(cfg, fg("chrome.exe", YOUTUBE), clock)
    tracker.tick()
    clock.advance(10)
    tracker.tick()                             # heartbeat now t0+10
    assert get_meta(db, HEARTBEAT_KEY) is not None
    assert get_meta(db, OPEN_SESSION_KEY)      # open session persisted

    # simulate abrupt crash: new tracker on the same DB
    tracker2 = ActivityTracker(db, osa, cfg, clock=clock)
    saved = rows(db)
    assert len(saved) == 1
    assert saved[0]["duration_seconds"] == 10  # closed at last heartbeat
    assert get_meta(db, OPEN_SESSION_KEY) == ""
    db.close()


def test_lock_screen_treated_as_away(cfg):
    clock = Clock(DAY1)
    tracker, db, osa = make(cfg, fg("chrome.exe", YOUTUBE), clock)
    tracker.tick()
    clock.advance(10)
    osa.foreground = None                      # lock screen
    tracker.tick()
    saved = rows(db)
    assert len(saved) == 1 and saved[0]["duration_seconds"] == 10
    db.close()
