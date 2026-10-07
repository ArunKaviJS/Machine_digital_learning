"""Tests for backend/db: schema, migrations, repositories."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import open_db
from backend.db.connection import Database, get_meta, set_meta
from backend.db.migrations import current_version, migrate
from backend.db.repositories.ai_repo import AiRepo
from backend.db.repositories.guard_repo import GuardRepo
from backend.db.repositories.tidy_repo import TidyRepo
from backend.db.repositories.usage_repo import UsageRepo
from backend.db.repositories.water_repo import WaterRepo

TABLES = {"usage_sessions", "water_events", "tidy_batches", "tidy_moves",
          "guard_events", "ai_calls", "meta"}


def table_names(db: Database) -> set[str]:
    rows = db.query("SELECT name FROM sqlite_master WHERE type='table'")
    return {r["name"] for r in rows}


# ---- schema & migrations ----

def test_fresh_memory_db_has_schema():
    db = Database(":memory:")
    migrate(db.raw)
    assert TABLES <= table_names(db)
    assert get_meta(db, "schema_version") == "1"
    db.close()


def test_migrate_is_idempotent():
    db = Database(":memory:")
    v1 = migrate(db.raw)
    v2 = migrate(db.raw)
    assert v1 == v2 == 1
    assert current_version(db.raw) == 1
    db.close()


def test_migrate_file_db_roundtrip(tmp_path: Path):
    path = tmp_path / "arun.db"
    db = open_db(path=path)
    set_meta(db, "heartbeat", "2026-10-07T10:00:00")
    db.close()
    db2 = open_db(path=path)  # reopen: data persists, no duplicate work
    assert get_meta(db2, "heartbeat") == "2026-10-07T10:00:00"
    assert get_meta(db2, "schema_version") == "1"
    db2.close()


def test_transaction_rollback():
    db = Database(":memory:")
    migrate(db.raw)
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.execute("INSERT INTO meta(key, value) VALUES('a','1')")
            raise RuntimeError("boom")
    assert get_meta(db, "a") is None
    db.close()


# ---- usage repo ----

@pytest.fixture()
def usage_db():
    db = Database(":memory:")
    migrate(db.raw)
    repo = UsageRepo(db)
    repo.insert_session("chrome", "2026-10-06T09:00:00", "2026-10-06T10:00:00",
                        3600, "2026-10-06", website="youtube.com")
    repo.insert_session("chrome", "2026-10-06T11:00:00", "2026-10-06T11:30:00",
                        1800, "2026-10-06", website="youtube.com")
    repo.insert_session("Code", "2026-10-06T14:00:00", "2026-10-06T15:00:00",
                        3600, "2026-10-06")
    repo.insert_session("chrome", "2026-10-07T08:00:00", "2026-10-07T08:10:00",
                        600, "2026-10-07", website="youtube.com")
    yield repo, db
    db.close()


def test_usage_sum_and_filters(usage_db):
    repo, _ = usage_db
    assert repo.sum_seconds("2026-10-06", "2026-10-06") == 9000
    assert repo.sum_seconds("2026-10-06", "2026-10-07", website="youtube.com") == 6000
    assert repo.sum_seconds("2026-10-06", "2026-10-07", application="Code") == 3600
    assert repo.sum_seconds("2026-10-08", "2026-10-09") == 0


def test_usage_top_app_and_longest(usage_db):
    repo, _ = usage_db
    assert repo.top_application("2026-10-06", "2026-10-06") == ("chrome", 5400)
    longest = repo.longest_session("2026-10-06", "2026-10-07")
    assert longest["application"] == "chrome"
    assert longest["duration_seconds"] == 3600
    assert repo.longest_session("2026-10-09", "2026-10-09") is None
    assert repo.top_application("2026-10-09", "2026-10-09") is None


def test_usage_active_hour_and_daily_totals(usage_db):
    repo, _ = usage_db
    hour, secs = repo.most_active_hour("2026-10-06", "2026-10-07")
    assert hour == 9 and secs == 3600
    totals = repo.daily_totals("2026-10-05", "2026-10-07", website="youtube.com")
    assert totals == {"2026-10-05": 0, "2026-10-06": 5400, "2026-10-07": 600}


# ---- water repo ----

def test_water_repo_roundtrip():
    db = Database(":memory:")
    migrate(db.raw)
    repo = WaterRepo(db)
    repo.add("2026-10-07T09:00:00", "2026-10-07", "reminder_shown")
    repo.add("2026-10-07T09:01:00", "2026-10-07", "drank")
    repo.add("2026-10-07T10:00:00", "2026-10-07", "drank")
    assert repo.count_drunk("2026-10-07") == 2
    assert repo.count_drunk("2026-10-06") == 0
    assert repo.last_of_type("drank")["date"] == "2026-10-07"
    assert repo.last(("reminder_shown",))["type"] == "reminder_shown"
    assert len(repo.events_on("2026-10-07")) == 3
    with pytest.raises(ValueError):
        repo.add("2026-10-07T10:00:00", "2026-10-07", "exploded")
    db.close()


# ---- tidy repo ----

def test_tidy_repo_confirm_and_undo():
    db = Database(":memory:")
    migrate(db.raw)
    repo = TidyRepo(db)
    batch = repo.create_batch("downloads", "2026-10-07T10:00:00")
    repo.confirm_batch(batch)
    repo.add_move(batch, r"C:\dl\a.png", r"C:\dl\Images\a.png", "2026-10-07T10:00:01")
    repo.add_move(batch, r"C:\dl\b.mp4", r"C:\dl\Videos\b.mp4", "2026-10-07T10:00:02")
    assert len(repo.moves_of_batch(batch)) == 2
    assert repo.last_undoable_batch()["id"] == batch
    repo.mark_undone(batch)
    assert repo.last_undoable_batch() is None
    moves = repo.moves_of_batch(batch)
    assert all(m["undone"] == 1 for m in moves)
    db.close()


def test_tidy_unconfirmed_batch_not_undoable():
    db = Database(":memory:")
    migrate(db.raw)
    repo = TidyRepo(db)
    repo.create_batch("downloads", "2026-10-07T10:00:00")
    assert repo.last_undoable_batch() is None
    db.close()


# ---- guard repo ----

def test_guard_repo_events_and_streak():
    db = Database(":memory:")
    migrate(db.raw)
    repo = GuardRepo(db)
    repo.add_event("2026-10-07T10:00:00", "2026-10-07", "nag", site="youtube.com")
    repo.add_event("2026-10-07T10:25:00", "2026-10-07", "tab_closed", site="youtube.com")
    assert [e["type"] for e in repo.recent()] == ["tab_closed", "nag"]
    assert len(repo.events_on("2026-10-07")) == 2
    with pytest.raises(ValueError):
        repo.add_event("2026-10-07T10:00:00", "2026-10-07", "wrong")
    repo.set_streak(900, "2026-10-07T09:45:00")
    assert repo.get_streak() == 900
    assert repo.get_streak_since() == "2026-10-07T09:45:00"
    db.close()


# ---- ai repo ----

def test_ai_repo_log_and_stats():
    db = Database(":memory:")
    migrate(db.raw)
    repo = AiRepo(db)
    repo.log_call("2026-10-07T10:00:00", "usage_query", 420, True, prompt=None)
    repo.log_call("2026-10-07T10:01:00", None, 900, False)
    stats = repo.stats()
    assert stats == {"calls": 2, "avg_ms": 660, "successes": 1}
    recent = repo.recent()
    assert recent[0]["success"] == 0
    assert "prompt" not in recent[0]  # prompt never returned by recent()
    db.close()
