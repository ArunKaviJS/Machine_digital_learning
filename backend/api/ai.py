"""POST /ai/warm and /ai/unload — load the model when the chat opens (so the
first message isn't a ~10 s cold start) and free its RAM when the chat
closes. Both return at once; the work runs in the background."""

from __future__ import annotations

import threading

from fastapi import APIRouter, Request

router = APIRouter()


def _in_background(request: Request, method: str) -> bool:
    gateway = getattr(request.app.state, "ai_gateway", None)
    if gateway is None:
        return False
    threading.Thread(target=getattr(gateway.client, method), name=f"llm-{method}",
                     daemon=True).start()
    return True


@router.post("/ai/warm")
def warm(request: Request) -> dict[str, bool]:
    return {"ok": _in_background(request, "warm_up")}


@router.post("/ai/unload")
def unload(request: Request) -> dict[str, bool]:
    return {"ok": _in_background(request, "unload")}
