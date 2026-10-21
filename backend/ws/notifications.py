"""NotificationManager: fan-out of server -> client events (SKILL §13/§18)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("arun.notifications")


class NotificationManager:
    """Registry of connected /ws/events clients + async broadcast."""

    def __init__(self) -> None:
        self._clients: set = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def connect(self, ws) -> None:
        self._clients.add(ws)
        try:  # remember the server loop so worker threads can push events
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

    def disconnect(self, ws) -> None:
        self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def broadcast(self, payload: dict[str, Any]) -> int:
        """Send payload to every connected client; drops dead sockets."""
        if not self._clients:
            return 0
        sent = 0
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                logger.debug("dropping dead websocket client")
                self._clients.discard(ws)
        return sent

    def broadcast_soon(self, payload: dict[str, Any]) -> None:
        """Fire-and-forget broadcast from sync code inside the event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop (sync tests): nobody is listening anyway
        loop.create_task(self.broadcast(payload))

    def broadcast_from_thread(self, payload: dict[str, Any]) -> bool:
        """Push an event from a worker thread (sync endpoints run in a
        thread pool, where broadcast_soon finds no loop and silently drops
        it). True if handed to the server loop."""
        if self._loop is None or not self._clients or self._loop.is_closed():
            return False
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), self._loop)
        return True
