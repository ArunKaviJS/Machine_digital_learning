"""Tests for Arun API security (token auth, CORS/Origin restriction, WS auth)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.main import create_app


@pytest.fixture()
def unauthed_client(cfg: dict) -> TestClient:
    app = create_app(cfg, start_services=False)
    # Plain client with NO headers by default
    with TestClient(app) as c:
        c.app.state.ai_gateway = None
        yield c


def test_health_open_without_token(unauthed_client: TestClient):
    r = unauthed_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_get_quick_questions_open_without_token(unauthed_client: TestClient):
    r = unauthed_client.get("/quick-questions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_post_missing_token_returns_401(unauthed_client: TestClient):
    r = unauthed_client.post("/water/drink")
    assert r.status_code == 401
    assert "Missing" in r.json()["detail"]


def test_post_wrong_token_returns_403(unauthed_client: TestClient):
    r = unauthed_client.post(
        "/water/drink",
        headers={"X-Arun-Token": "completely-wrong-token"},
    )
    assert r.status_code == 403
    assert "Invalid" in r.json()["detail"]


def test_post_correct_token_works(unauthed_client: TestClient):
    token = unauthed_client.app.state.api_token
    r = unauthed_client.post(
        "/water/drink",
        headers={"X-Arun-Token": token},
    )
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_reject_request_with_web_origin(unauthed_client: TestClient):
    token = unauthed_client.app.state.api_token
    # Even with a valid token, web origin must be rejected (no CORS)
    r = unauthed_client.post(
        "/water/drink",
        headers={
            "X-Arun-Token": token,
            "Origin": "http://malicious-website.com",
        },
    )
    assert r.status_code == 403
    assert "Cross-origin" in r.json()["detail"]

    # Also rejected on GET
    r2 = unauthed_client.get(
        "/health",
        headers={"Origin": "https://random-site.org"},
    )
    assert r2.status_code == 403


def test_ws_missing_token_closes_with_4401(unauthed_client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc:
        with unauthed_client.websocket_connect("/ws/events"):
            pass
    assert exc.value.code == 4401


def test_ws_wrong_token_closes_with_4403(unauthed_client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc:
        with unauthed_client.websocket_connect("/ws/events?token=bogus"):
            pass
    assert exc.value.code == 4403


def test_ws_correct_token_connects(unauthed_client: TestClient):
    token = unauthed_client.app.state.api_token
    with unauthed_client.websocket_connect(f"/ws/events?token={token}"):
        assert unauthed_client.app.state.notifications.client_count == 1
    assert unauthed_client.app.state.notifications.client_count == 0


def test_ws_web_origin_rejected_with_1008(unauthed_client: TestClient):
    token = unauthed_client.app.state.api_token
    with pytest.raises(WebSocketDisconnect) as exc:
        with unauthed_client.websocket_connect(
            f"/ws/events?token={token}",
            headers={"Origin": "https://malicious-site.com"},
        ):
            pass
    assert exc.value.code == 1008
