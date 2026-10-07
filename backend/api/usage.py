"""Usage endpoints (SKILL §18): GET /usage/summary."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query, Request

from backend.config import VALID_PERIODS
from backend.services.usage_service import UsageService

router = APIRouter()


@router.get("/usage/summary")
def usage_summary(
    request: Request,
    period: str = Query(default="today"),
) -> dict[str, Any]:
    """Get usage summary for a period (totals per site, top apps, total time)."""
    if period not in VALID_PERIODS:
        raise HTTPException(
            400,
            f"Invalid period '{period}'. Allowed: {sorted(VALID_PERIODS)}.",
        )
    svc = UsageService(request.app.state.db)
    return svc.summary(period)
