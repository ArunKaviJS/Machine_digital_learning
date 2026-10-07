"""Tests for Quick Questions: catalogue, all 11 IDs, templates, error path."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.db.connection import Database
from backend.db.migrations import migrate
from backend.db.repositories.usage_repo import UsageRepo
from backend.db.repositories.water_repo import WaterRepo
from backend.main import create_app
from backend.router.quick import KNOWN_IDS, QUICK_QUESTIONS, UnknownQuestion, quick_answer
from backend.router.templates import fmt_duration, fmt_hour

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture()
def seeded_db():
    db = Database(":memory:")
    migrate(db.raw)
    usage = UsageRepo(db)
    usage.insert_session("Chrome", f"{TODAY}T09:00:00+05:30", f"{TODAY}T10:00:00+05:30",
                         7200, TODAY, website="youtube.com")   # 2h -> warn
    usage.insert_session("Code", f"{TODAY}T14:00:00+05:30", f"{TODAY}T14:30:00+05:30",
                         1800, TODAY)
    usage.insert_session("Chrome", f"{YESTERDAY}T09:00:00+05:30", f"{YESTERDAY}T10:00:00+05:30",
                         1800, YESTERDAY, website="youtube.com")
    water = WaterRepo(db)
    water.add(f"{TODAY}T09:00:00+05:30", TODAY, "reminder_shown")
    water.add(f"{TODAY}T09:01:00+05:30", TODAY, "drank")
    water.add(f"{TODAY}T10:00:00+05:30", TODAY, "drank")
    yield db
    db.close()


@pytest.fixture()
def client(cfg, seeded_db):  # noqa: F811
    app = create_app(cfg, start_services=False)
    with TestClient(app, headers={"X-Arun-Token": app.state.api_token}) as c:
        app.state.db = seeded_db  # replace the lifespan DB with the seeded one
        yield c


# ---- catalogue ----

def test_catalogue_is_the_contract(client: TestClient):
    body = client.get("/quick-questions").json()
    assert [q["id"] for q in body] == KNOWN_IDS
    assert len(body) == 11
    assert all(q["category"] in {"USAGE", "PRODUCTIVITY", "WATER"} for q in body)


def test_catalogue_matches_spec_ids():
    expected = {
        "youtube_usage_today", "youtube_usage_yesterday", "youtube_usage_week",
        "top_app_today", "top_app_week", "screen_time_today",
        "longest_session_today", "most_active_hour_today",
        "compare_today_yesterday", "water_today", "last_water_reminder",
    }
    assert set(KNOWN_IDS) == expected
    assert len(QUICK_QUESTIONS) == 11


# ---- every ID answers 200 with a sane envelope ----

def test_all_ids_answer(client: TestClient):
    for q in QUICK_QUESTIONS:
        resp = client.post("/ask/quick", json={"question_id": q["id"]})
        assert resp.status_code == 200, q["id"]
        body = resp.json()
        assert body["text"], q["id"]
        assert body["animation"] in {"idle", "walk", "smile", "wave", "warn",
                                     "angry", "happy", "water"}
        assert body["needs_confirmation"] is False
        assert body["proposal_id"] is None
        assert isinstance(body["data"], dict)


def test_unknown_id_is_400(client: TestClient):
    resp = client.post("/ask/quick", json={"question_id": "nope"})
    assert resp.status_code == 400


# ---- correct numbers/text for key questions ----

def test_youtube_today_uses_real_data(client: TestClient):
    body = client.post("/ask/quick", json={"question_id": "youtube_usage_today"}).json()
    assert body["data"]["seconds"] == 7200
    assert "2h" in body["text"] and "YouTube" in body["text"] and "today" in body["text"]
    assert body["animation"] == "warn"          # >= 2h threshold


def test_yesterday_youtube(client: TestClient):
    body = client.post("/ask/quick", json={"question_id": "youtube_usage_yesterday"}).json()
    assert body["data"]["seconds"] == 1800
    assert "30m" in body["text"] and "yesterday" in body["text"]


def test_top_app_today(client: TestClient):
    body = client.post("/ask/quick", json={"question_id": "top_app_today"}).json()
    assert body["data"]["application"] == "Chrome"
    assert body["data"]["seconds"] == 7200      # Chrome-only rows today (Code is 1800)


def test_screen_time_today(client: TestClient):
    body = client.post("/ask/quick", json={"question_id": "screen_time_today"}).json()
    assert body["data"]["seconds"] == 9000      # 7200 + 1800
    assert "2h 30m" in body["text"]


def test_longest_session_today(client: TestClient):
    body = client.post("/ask/quick", json={"question_id": "longest_session_today"}).json()
    assert body["data"]["seconds"] == 7200
    assert body["data"]["site_label"] == "YouTube"


def test_most_active_hour_today(client: TestClient):
    body = client.post("/ask/quick", json={"question_id": "most_active_hour_today"}).json()
    assert body["data"]["hour"] == 9
    assert "9 AM" in body["text"]


def test_compare_today_yesterday(client: TestClient):
    body = client.post("/ask/quick", json={"question_id": "compare_today_yesterday"}).json()
    # today 9000, yesterday 1800 -> +7200 -> warn
    assert body["data"]["today_seconds"] == 9000
    assert body["data"]["yesterday_seconds"] == 1800
    assert body["data"]["diff"] == 7200
    assert body["animation"] == "warn"
    assert "2h" in body["text"] and "more than yesterday" in body["text"]


def test_water_today(client: TestClient):
    body = client.post("/ask/quick", json={"question_id": "water_today"}).json()
    assert body["data"]["count"] == 2
    assert body["data"]["target"] == 8
    assert "2 of 8" in body["text"]


def test_last_water_reminder(client: TestClient):
    body = client.post("/ask/quick", json={"question_id": "last_water_reminder"}).json()
    assert body["data"]["time"] == "09:00"
    assert "09:00" in body["text"]


# ---- empty-data wording + formatters ----

def test_empty_db_answers_friendly(cfg):
    db = Database(":memory:")
    migrate(db.raw)
    for qid in KNOWN_IDS:
        result = quick_answer(qid, db, cfg)
        assert result["text"]
        assert result["animation"] in {"idle", "smile", "happy", "water"}
        assert result["needs_confirmation"] is False
    with pytest.raises(UnknownQuestion):
        quick_answer("not_a_question", db, cfg)
    db.close()


@pytest.mark.parametrize(
    "minutes,expected",
    [(0, "0m"), (45, "45m"), (59, "59m"), (60, "1h"), (155, "2h 35m"),
     (61, "1h 1m"), (120, "2h"), (1440, "24h")],
)
def test_fmt_duration(minutes, expected):
    assert fmt_duration(minutes) == expected


def test_fmt_secs_from_db_seconds():
    from backend.router.templates import fmt_secs
    assert fmt_secs(0) == "0m"
    assert fmt_secs(45) == "1m"          # rounds to nearest minute
    assert fmt_secs(155 * 60) == "2h 35m"
    assert fmt_secs(3600) == "1h"


@pytest.mark.parametrize("hour,expected", [(0, "12 AM"), (9, "9 AM"), (12, "12 PM"),
                                           (13, "1 PM"), (23, "11 PM")])
def test_fmt_hour(hour, expected):
    assert fmt_hour(hour) == expected
