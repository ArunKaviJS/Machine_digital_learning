"""WebSocket client (SKILL §18): backend push events -> Qt signals.

Runs its own asyncio event loop on a background QThread (mirrors the
per-call QThread pattern in api_client.py) and reconnects with a short
backoff if the backend isn't up yet or the connection drops.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import websockets
from PyQt6.QtCore import QObject, QThread, pyqtSignal

logger = logging.getLogger("arun.client.ws")

RECONNECT_SECONDS = 3.0


class _Worker(QObject):
    # NOT named `event`: that shadows QObject.event(QEvent) -> bool, Qt's
    # own core event-dispatch method, and corrupts the object silently.
    message = pyqtSignal(dict)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._stop = False

    def run(self) -> None:
        asyncio.run(self._loop())

    async def _loop(self) -> None:
        while not self._stop:
            try:
                async with websockets.connect(self.url, open_timeout=5) as ws:
                    async for message in ws:
                        try:
                            payload = json.loads(message)
                        except ValueError:
                            continue
                        if isinstance(payload, dict):
                            self.message.emit(payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("ws connection dropped: %s", exc)
            if not self._stop:
                await asyncio.sleep(RECONNECT_SECONDS)

    def stop(self) -> None:
        self._stop = True


class EventClient(QObject):
    """base_url + token from config; emits `message` for each server push."""

    message = pyqtSignal(dict)

    def __init__(self, config: dict[str, Any]):
        super().__init__()
        host = config["backendHost"]
        port = config["backendPort"]
        token = config.get("apiToken", "")
        url = f"ws://{host}:{port}/ws/events?token={token}"
        self._thread = QThread()
        self._worker = _Worker(url)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.message.connect(self.message)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(2000)
