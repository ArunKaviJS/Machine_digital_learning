"""Quick Questions endpoints: GET /quick-questions, POST /ask/quick (SKILL §18)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.router.quick import QUICK_QUESTIONS, UnknownQuestion, quick_answer

router = APIRouter()


class QuickAskRequest(BaseModel):
    question_id: str


@router.get("/quick-questions")
def list_quick_questions() -> list[dict[str, str]]:
    return QUICK_QUESTIONS


@router.post("/ask/quick")
def ask_quick(body: QuickAskRequest, request: Request) -> dict:
    app = request.app
    try:
        return quick_answer(body.question_id, app.state.db, app.state.config)
    except UnknownQuestion:
        raise HTTPException(status_code=400, detail=f"unknown question_id: {body.question_id}")
