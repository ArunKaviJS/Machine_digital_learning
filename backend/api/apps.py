"""POST /apps/idle/answer — the user's reply to "shall I close X?"."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class IdleAnswer(BaseModel):
    key: str = Field(..., min_length=1, max_length=300)
    close: bool


class IdleAnswerResponse(BaseModel):
    text: str
    animation: str


@router.post("/apps/idle/answer", response_model=IdleAnswerResponse)
def idle_answer(body: IdleAnswer, request: Request) -> IdleAnswerResponse:
    service = getattr(request.app.state, "idle_apps", None)
    if service is None:
        raise HTTPException(503, "Idle-app reminders are not ready.")
    return IdleAnswerResponse(**service.answer(body.key, body.close))
