"""Tests for M10b client endpoints: /usage/summary, /settings, /data/clear, /system/autostart."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.db.repositories.usage_repo import UsageRepo
from backend.db.repositories.water_repo import WaterRepo
from backend.main import create_app
from tests.fakes import FakeOSAdapter

TODAY = "2026-10-07"


@pytest.fixture()
def client_with_data(cfg: dict, tmp_path: Path):
    user_cfg_path = tmp_path / "user_config.json"
    user_cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    app = create_app(cfg, start_services=False)
    app.state.user_config_path = user_cfg_path
    fake_adapter = FakeOSAdapter()
    app.state.os_adapter = fake_adapter

    with TestClient(app, headers={"X-Arun-Token": app.state.api_token}) as c:
        c.app.state.ai_gateway = None

        # Seed data (app.state.db only exists once the lifespan has started)
        usage = UsageRepo(app.state.db)
        usage.insert_session(
            application="Google Chrome",
            website="youtube.com",
            start_time=f"{TODAY}T10:00:00+05:30",
            end_time=f"{TODAY}T10:30:00+05:30",
            duration_seconds=1800,
            date=TODAY,
        )
        usage.insert_session(
            application="VS Code",
            start_time=f"{TODAY}T11:00:00+05:30",
            end_time=f"{TODAY}T12:00:00+05:30",
            duration_seconds=3600,
            date=TODAY,
        )

        water = WaterRepo(app.state.db)
        water.add(f"{TODAY}T10:00:00+05:30", TODAY, "drank")

        yield c, fake_adapter


# ---- /usage/summary ----

def test_usage_summary_today(client_with_data):
    client, _ = client_with_data
    r = client.get("/usage/summary?period=today")
    assert r.status_code == 200
    body = r.json()
    assert body["period"] == "today"
    assert body["total_seconds"] == 5400
    assert any(s["site"] == "youtube.com" for s in body["sites"])
    assert any(a["application"] == "VS Code" for a in body["apps"])


def test_usage_summary_invalid_period(client_with_data):
    client, _ = client_with_data
    r = client.get("/usage/summary?period=bogus")
    assert r.status_code == 400
    assert "Invalid period" in r.json()["detail"]


# ---- /settings ----

def test_get_settings(client_with_data):
    client, _ = client_with_data
    r = client.get("/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["userName"] == "Arun"
    assert "apiToken" not in body


def test_put_settings_valid_no_restart(client_with_data):
    client, _ = client_with_data
    r = client.put("/settings", json={"waterIntervalMinutes": 30, "userName": "Kavi"})
    assert r.status_code == 200
    body = r.json()
    assert body["restart_required"] is False
    assert body["settings"]["waterIntervalMinutes"] == 30
    assert body["settings"]["userName"] == "Kavi"


def test_put_settings_triggers_restart_required(client_with_data):
    client, _ = client_with_data
    r = client.put("/settings", json={"backendPort": 9999})
    assert r.status_code == 200
    body = r.json()
    assert body["restart_required"] is True
    assert body["settings"]["backendPort"] == 9999


def test_put_settings_rejects_unknown_keys(client_with_data):
    client, _ = client_with_data
    r = client.put("/settings", json={"nonExistentSetting": 123})
    assert r.status_code == 400
    assert "Unknown configuration key" in r.json()["detail"]


def test_put_settings_rejects_unknown_ai_keys(client_with_data):
    client, _ = client_with_data
    r = client.put("/settings", json={"ai": {"superSecretModel": "gpt-5"}})
    assert r.status_code == 400
    assert "Unknown ai key" in r.json()["detail"]


def test_put_settings_validation_failure(client_with_data):
    client, _ = client_with_data
    r = client.put("/settings", json={"fps": -10})
    assert r.status_code == 422


# ---- /data/clear ----

def test_data_clear_requires_confirmation(client_with_data):
    client, _ = client_with_data
    r = client.post("/data/clear", json={"confirm": False})
    assert r.status_code == 400
    assert "Confirmation required" in r.json()["detail"]


def test_data_clear_success(client_with_data):
    client, _ = client_with_data
    r = client.post("/data/clear", json={"confirm": True})
    assert r.status_code == 200
    assert r.json()["cleared"] is True

    # Usage summary should now be 0
    r_sum = client.get("/usage/summary?period=today")
    assert r_sum.json()["total_seconds"] == 0


# ---- /system/autostart ----

def test_system_autostart(client_with_data):
    client, fake_adapter = client_with_data
    r = client.post("/system/autostart", json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert fake_adapter.autostart is True

    r2 = client.post("/system/autostart", json={"enabled": False})
    assert r2.status_code == 200
    assert r2.json()["enabled"] is False
    assert fake_adapter.autostart is False
