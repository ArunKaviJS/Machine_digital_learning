"""POST /ask — free-text questions (SKILL §7: router → services → template)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.router.confirmations import PendingConfirmation
from backend.router.router import QuestionRouter
from backend.router.schemas import AskResponse

router = APIRouter()


class AskRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request) -> AskResponse:
    app = request.app.state
    router_obj = QuestionRouter(
        db=app.db,
        config=app.config,
        ai_gateway=getattr(app, "ai_gateway", None),
        pending=app.pending,
        tidy_service=getattr(app, "tidy_service", None),
        os_adapter=getattr(app, "os_adapter", None),
    )
    return AskResponse(**router_obj.ask(body.text))
