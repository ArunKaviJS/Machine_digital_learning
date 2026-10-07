"""Guard endpoints (SKILL §15, §18): cancel, snooze, status, pause, resume."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Request

from backend.services.guard_service import GuardService

router = APIRouter()


def _guard(request: Request) -> GuardService:
    guard = getattr(request.app.state, "guard", None)
    if guard is None:
        raise HTTPException(503, "Guard service is not ready.")
    return guard


@router.get("/guard/status")
def guard_status(request: Request) -> dict[str, Any]:
    """Get current distraction guard status: state, site, streak, seconds_left, paused."""
    return _guard(request).get_status()


@router.post("/guard/cancel")
def guard_cancel(request: Request) -> dict[str, Any]:
    """Cancel the active countdown/nag session."""
    return _guard(request).cancel()


@router.post("/guard/snooze")
def guard_snooze(request: Request) -> dict[str, Any]:
    """Snooze distraction closing by +5 minutes."""
    return _guard(request).snooze(seconds=300.0)


@router.post("/pause")
def pause(request: Request) -> dict[str, Any]:
    """Enable manual Do Not Disturb mode (silences guard, water loop, nags)."""
    return _guard(request).pause()


@router.post("/resume")
def resume(request: Request) -> dict[str, Any]:
    """Disable manual Do Not Disturb mode."""
    return _guard(request).resume()
