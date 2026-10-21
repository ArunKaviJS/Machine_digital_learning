"""POST /character/done/{id} — the client's paw pressed the button (see
backend/services/character_service.py)."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.post("/character/done/{act_id}")
def character_done(act_id: str, request: Request) -> dict[str, bool]:
    character = getattr(request.app.state, "character", None)
    return {"ok": bool(character and character.done(act_id))}
