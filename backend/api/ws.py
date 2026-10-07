"""WS /ws/events (SKILL §18): server -> client push channel."""

from __future__ import annotations

import secrets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket) -> None:
    # 1. Reject cross-origin web origins
    origin = ws.headers.get("origin")
    if origin is not None and origin.strip():
        await ws.close(code=1008, reason="Cross-origin forbidden")
        return

    # 2. Require API token via query param
    expected = getattr(ws.app.state, "api_token", None)
    token = ws.query_params.get("token") or ws.query_params.get("arun_token")
    if not token:
        await ws.close(code=4401, reason="Missing token")
        return
    if not expected or not secrets.compare_digest(token, expected):
        await ws.close(code=4403, reason="Invalid token")
        return

    await ws.accept()
    notifications = ws.app.state.notifications
    notifications.connect(ws)
    try:
        while True:
            await ws.receive_text()  # client pings/ignored messages keep it open
    except WebSocketDisconnect:
        pass
    finally:
        notifications.disconnect(ws)
