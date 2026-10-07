"""Tests for backend/main.py: /health and app factory."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import create_app


def test_health_ok(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["ai"]["enabled"] is True
    assert isinstance(body["ai"]["available"], bool)


def test_health_ai_disabled(cfg: dict, monkeypatch):
    cfg["ai"]["enabled"] = False
    called = []
    monkeypatch.setattr("backend.main.httpx.get", lambda *a, **k: called.append(1))
    with TestClient(create_app(cfg)) as client:
        body = client.get("/health").json()
    assert body["ai"] == {"enabled": False, "available": False}
    assert called == []  # never pings Ollama when AI is off


def test_health_reports_ai_unreachable(cfg: dict, monkeypatch):
    import httpx

    def boom(*args, **kwargs):
        raise httpx.ConnectError("no ollama")

    monkeypatch.setattr("backend.main.httpx.get", boom)
    with TestClient(create_app(cfg)) as client:
        body = client.get("/health").json()
    assert body["ai"]["available"] is False
    assert body["status"] == "ok"  # Ollama down must not break the backend
