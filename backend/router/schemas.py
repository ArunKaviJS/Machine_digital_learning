"""Pydantic response shape for /ask (SKILL §7) — the API boundary only.

QuestionRouter itself stays pure and returns plain dicts (testable without
FastAPI); this model validates/serialises that dict at the HTTP edge.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AskResponse(BaseModel):
    text: str
    animation: str
    needs_confirmation: bool = False
    proposal_id: str | None = None
    data: dict[str, Any] = {}
