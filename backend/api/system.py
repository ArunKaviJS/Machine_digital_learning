"""System endpoints (SKILL §18, §22): POST /system/autostart."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.os_integration.factory import get_os_adapter

router = APIRouter()


class AutostartRequest(BaseModel):
    enabled: bool


@router.post("/system/autostart")
def set_autostart(body: AutostartRequest, request: Request) -> dict[str, Any]:
    """Enable or disable start-at-login in Windows registry."""
    adapter = getattr(request.app.state, "os_adapter", None)
    if adapter is None:
        adapter = get_os_adapter(request.app.state.config)
    try:
        adapter.set_autostart(body.enabled)
    except Exception as exc:
        raise HTTPException(500, f"Failed to set autostart: {exc}") from exc
    return {"enabled": body.enabled, "status": "ok"}
