"""Unused-app reminder scheduler: async loop around IdleAppService.tick().

step() never sleeps so tests can drive it; run() sleeps between steps and
exits cleanly on cancellation (same shape as WaterLoop).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("arun.idle_apps")


class IdleAppLoop:
    def __init__(self, service, notifications, tick_seconds: float = 30.0):
        self.service = service
        self.notifications = notifications
        self.tick_seconds = tick_seconds

    async def step(self) -> list[dict[str, Any]]:
        events = self.service.tick()
        for payload in events:
            await self.notifications.broadcast(payload)
        return events

    async def run(self) -> None:
        logger.info("idle-app loop started (tick=%ss)", self.tick_seconds)
        while True:
            await asyncio.sleep(self.tick_seconds)
            try:
                await self.step()
            except asyncio.CancelledError:
                logger.info("idle-app loop stopped")
                raise
            except Exception:
                logger.exception("idle-app loop step failed")
