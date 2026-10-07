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
    tracker_task = None
    if getattr(app.state, "start_services", True):
        from backend.os_integration.factory import get_os_adapter
        from backend.tracker.activity_tracker import ActivityTracker

        app.state.tracker = ActivityTracker(app.state.db, get_os_adapter(cfg), cfg)
        tracker_task = asyncio.create_task(app.state.tracker.run())
    logger.info(
        "backend starting on %s:%s (ai.enabled=%s, model=%s)",
        cfg["backendHost"], cfg["backendPort"],
        cfg["ai"]["enabled"], cfg["ai"]["model"],
    )
    yield
    if tracker_task:
        tracker_task.cancel()
        app.state.tracker.close()
    app.state.db.close()
    logger.info("backend shutting down")


def create_app(config: dict[str, Any] | None = None,
               start_services: bool = True) -> FastAPI:
    app = FastAPI(title="Arun backend", version="0.1.0", lifespan=lifespan)
    app.state.config = config if config is not None else load_config()
    app.state.start_services = start_services
    app.state.ai_check = {"at": 0.0, "available": False}

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
