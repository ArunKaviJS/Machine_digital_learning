"""Water endpoints (SKILL §18): /water/drink · /water/snooze · /water/today."""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.services.water_service import WaterService

router = APIRouter()


def _service(request: Request) -> WaterService:
    return WaterService(request.app.state.db, request.app.state.config)


@router.post("/water/drink")
def drink(request: Request) -> dict:
    result = _service(request).drank()
    result["animation"] = "happy"
    return result


@router.post("/water/snooze")
def snooze(request: Request) -> dict:
    return _service(request).snooze()


@router.get("/water/today")
def today(request: Request) -> dict:
    return _service(request).today_summary()
