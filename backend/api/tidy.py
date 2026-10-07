"""Tidy endpoints (SKILL §18): propose / confirm / undo."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.services.tidy_service import TidyError

router = APIRouter()


class ProposeRequest(BaseModel):
    folder: str = Field(..., min_length=1, max_length=40)


class ConfirmRequest(BaseModel):
    proposal_id: int


def _svc(request: Request):
    svc = getattr(request.app.state, "tidy_service", None)
    if svc is None:
        raise HTTPException(503, "Tidy service is not ready.")
    return svc


def _call(request: Request, fn, *args):
    try:
        return fn(*args)
    except TidyError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.post("/tidy/propose")
def propose(body: ProposeRequest, request: Request) -> dict:
    return _call(request, _svc(request).propose, body.folder)


@router.post("/tidy/confirm")
def confirm(body: ConfirmRequest, request: Request) -> dict:
    return _call(request, _svc(request).confirm, body.proposal_id)


@router.post("/tidy/undo")
def undo(request: Request) -> dict:
    return _call(request, _svc(request).undo)
