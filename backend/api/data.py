"""Data management endpoints (SKILL §18, §23): POST /data/clear."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.db.connection import Database, set_meta

router = APIRouter()


class ClearDataRequest(BaseModel):
    confirm: bool = False


@router.post("/data/clear")
def clear_data(body: ClearDataRequest, request: Request) -> dict[str, Any]:
    """Clear all usage sessions, water events, guard events, and tidy records."""
    if not body.confirm:
        raise HTTPException(
            400,
            "Confirmation required to clear all data. Send {'confirm': true}.",
        )

    db: Database = request.app.state.db
    with db.transaction():
        db.execute("DELETE FROM usage_sessions")
        db.execute("DELETE FROM water_events")
        db.execute("DELETE FROM guard_events")
        db.execute("DELETE FROM tidy_moves")
        db.execute("DELETE FROM tidy_batches")
        db.execute("DELETE FROM ai_calls")
        set_meta(db, "guard.streak_seconds", "0")
        set_meta(db, "tracker.open_session", "")

    return {
        "cleared": True,
        "text": "All usage, water, guard, and tidy history has been cleared, bro.",
        "animation": "happy",
    }
