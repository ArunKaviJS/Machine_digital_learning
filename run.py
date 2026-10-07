"""Arun launcher: starts the backend (thread) then the client.

Usage:
  python run.py                 # backend + client (client falls back to a stub)
  python run.py --backend-only  # backend only, blocks (used by tests / dev)
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from typing import Any

from backend.config import ensure_user_config, load_config
from backend.logging_setup import setup_logging

logger = logging.getLogger("arun.run")


def _run_backend(cfg: dict[str, Any], api_token: str | None = None) -> None:
    import uvicorn

    from backend.main import create_app

    app = create_app(cfg, api_token=api_token)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=cfg["backendHost"],
            port=cfg["backendPort"],
            log_level="info",
            access_log=False,
        )
    )
    server.run()


def wait_for_health(cfg: dict[str, Any], timeout: float = 20.0) -> bool:
    import httpx

    url = f"http://{cfg['backendHost']}:{cfg['backendPort']}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=1.0).status_code == 200:
                return True
        except Exception:
            time.sleep(0.25)
    return False


def start_client(cfg: dict[str, Any]) -> None:
    try:
        from client.app import run_client  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "client not available yet (M11); run 'python run.py --backend-only' "
            "or open http://%s:%s/docs",
            cfg["backendHost"], cfg["backendPort"],
        )
        return
    run_client(cfg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arun")
    parser.add_argument("--backend-only", action="store_true",
                        help="run only the FastAPI backend")
    args = parser.parse_args(argv)

    setup_logging()
    ensure_user_config()
    cfg = load_config()
    import secrets
    api_token = secrets.token_urlsafe(32)
    cfg["apiToken"] = api_token
    logger.info("config loaded (user=%s)", cfg["userName"])

    if args.backend_only:
        logger.info("API token: %s", api_token)
        _run_backend(cfg, api_token=api_token)
        return 0

    thread = threading.Thread(target=_run_backend, args=(cfg, api_token), daemon=True,
                              name="arun-backend")
    thread.start()
    if not wait_for_health(cfg):
        logger.error("backend failed to become healthy")
        return 1
    start_client(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
