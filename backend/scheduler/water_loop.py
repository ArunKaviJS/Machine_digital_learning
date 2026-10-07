"""Water reminder scheduler (SKILL §16): async loop, DND/idle gated.

step() is a pure-ish unit (no sleeping) so tests can drive it with a fake
clock; run() sleeps between steps and exits cleanly on cancellation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("arun.water")


class WaterLoop:
    def __init__(self, service, notifications, os_adapter=None,
                 tick_seconds: float = 10.0):
        self.service = service
        self.notifications = notifications
        self.os_adapter = os_adapter
        self.tick_seconds = tick_seconds

    async def step(self) -> str:
        """One check: 'fired' | 'blocked' | 'not_due'."""
        if not self.service.due():
            return "not_due"
        if self.os_adapter is not None and self.service.blocked(self.os_adapter):
            return "blocked"  # retry next tick, do not log (§16)
        self.service.mark_reminder_shown()
        payload: dict[str, Any] = {
            "type": "water_due",
            "count": self.service.today_count(),
            "target": self.service.target,
        }
        await self.notifications.broadcast(payload)
        return "fired"

    async def run(self) -> None:
        logger.info("water loop started (tick=%ss)", self.tick_seconds)
        while True:
            await asyncio.sleep(self.tick_seconds)
            try:
                await self.step()
            except asyncio.CancelledError:
                logger.info("water loop stopped")
                raise
            except Exception:
                logger.exception("water loop step failed")
