"""FastAPI application factory for the Arun backend.

Run standalone:  python -m backend.main
Or via launcher: python run.py --backend-only
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

from backend.config import load_config
from backend.logging_setup import setup_logging

logger = logging.getLogger("arun.main")

AI_CHECK_TTL = 30.0  # seconds: how long /health caches the Ollama ping


def _ping_ai(cfg: dict[str, Any]) -> bool:
    """Cheap liveness check for Ollama; never raises."""
    ai = cfg.get("ai", {})
    if not ai.get("enabled"):
        return False
    try:
        resp = httpx.get(
            f"{ai['host'].rstrip('/')}/api/tags",
            timeout=min(2.0, float(ai.get("timeoutSeconds", 15))),
        )
        return resp.status_code == 200
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = app.state.config
    setup_logging()
    import asyncio

    from backend.db import open_db

    app.state.db = open_db(cfg)

    from backend.services.tidy_service import TidyService

    app.state.tidy_service = TidyService(app.state.db, cfg)
    if cfg.get("ai", {}).get("enabled"):
        from backend.services.ai_gateway import OllamaGateway

        app.state.ai_gateway = OllamaGateway(app.state.db, cfg)
    else:
        app.state.ai_gateway = None
    from backend.os_integration.factory import get_os_adapter
    from backend.services.guard_service import GuardService
    from backend.services.water_service import WaterService

    adapter = getattr(app.state, "os_adapter", None) or get_os_adapter(cfg)
    app.state.os_adapter = adapter
    app.state.guard = GuardService(app.state.db, cfg, adapter,
                                   notifications=app.state.notifications)
    from backend.services.idle_app_service import IdleAppService

    app.state.idle_apps = IdleAppService(cfg, adapter,
                                         is_paused=app.state.guard.is_paused)

    tracker_task = None
    water_task = None
    guard_task = None
    idle_apps_task = None
    if getattr(app.state, "start_services", True):
        from backend.scheduler.idle_app_loop import IdleAppLoop
        from backend.scheduler.water_loop import WaterLoop
        from backend.tracker.activity_tracker import ActivityTracker

        app.state.tracker = ActivityTracker(app.state.db, adapter, cfg)
        tracker_task = asyncio.create_task(app.state.tracker.run())
        water_loop = WaterLoop(WaterService(app.state.db, cfg),
                               app.state.notifications, adapter)
        water_task = asyncio.create_task(water_loop.run())
        guard_task = asyncio.create_task(app.state.guard.run())
        idle_apps_task = asyncio.create_task(
            IdleAppLoop(app.state.idle_apps, app.state.notifications).run())
    logger.info(
        "backend starting on %s:%s (ai.enabled=%s, model=%s)",
        cfg["backendHost"], cfg["backendPort"],
        cfg["ai"]["enabled"], cfg["ai"]["model"],
    )
    yield
    if tracker_task:
        tracker_task.cancel()
        app.state.tracker.close()
    if water_task:
        water_task.cancel()
    if guard_task:
        guard_task.cancel()
    if idle_apps_task:
        idle_apps_task.cancel()
    app.state.db.close()
    logger.info("backend shutting down")


def create_app(config: dict[str, Any] | None = None,
               start_services: bool = True,
               api_token: str | None = None) -> FastAPI:
    app = FastAPI(title="Arun backend", version="0.1.0", lifespan=lifespan)
    app.state.config = config if config is not None else load_config()
    app.state.start_services = start_services
    app.state.ai_check = {"at": 0.0, "available": False}
    from backend.security import SecurityMiddleware, generate_token
    token = api_token or app.state.config.get("apiToken") or generate_token()
    app.state.api_token = token
    app.state.config["apiToken"] = token
    app.add_middleware(SecurityMiddleware)

    from backend.api.apps import router as apps_router
    from backend.api.ask import router as ask_router
    from backend.api.data import router as data_router
    from backend.api.guard import router as guard_router
    from backend.api.quick import router as quick_router
    from backend.api.settings import router as settings_router
    from backend.api.system import router as system_router
    from backend.api.tidy import router as tidy_router
    from backend.api.usage import router as usage_router
    from backend.api.water import router as water_router
    from backend.api.ws import router as ws_router
    from backend.router.confirmations import PendingConfirmation
    from backend.ws.notifications import NotificationManager

    app.include_router(quick_router)
    app.include_router(ask_router)
    app.include_router(water_router)
    app.include_router(guard_router)
    app.include_router(tidy_router)
    app.include_router(usage_router)
    app.include_router(settings_router)
    app.include_router(data_router)
    app.include_router(system_router)
    app.include_router(ws_router)
    app.include_router(apps_router)
    app.state.pending = PendingConfirmation()
    app.state.notifications = NotificationManager()

    @app.get("/health")
    def health() -> dict[str, Any]:
        cfg = app.state.config
        cache = app.state.ai_check
        now = time.monotonic()
        if now - cache["at"] > AI_CHECK_TTL:
            cache["at"] = now
            cache["available"] = _ping_ai(cfg)
        return {
            "status": "ok",
            "version": app.version,
            "ai": {"enabled": cfg["ai"]["enabled"], "available": cache["available"]},
        }

    return app


app = create_app


def main() -> None:
    import uvicorn

    setup_logging()
    cfg = load_config()
    uvicorn.run(
        "backend.main:app",
        host=cfg["backendHost"],
        port=cfg["backendPort"],
        log_level="info",
    )


if __name__ == "__main__":
    main()
