"""Pending-confirmation store (SKILL §7 step 1, §23: expires after 2 minutes)."""

from __future__ import annotations

import time
from typing import Any, Callable

EXPIRY_SECONDS = 120


class PendingConfirmation:
    def __init__(self, clock: Callable[[], float] = time.time,
                 expiry: int = EXPIRY_SECONDS):
        self.clock = clock
        self.expiry = expiry
        self._payload: dict[str, Any] | None = None
        self._expires_at = 0.0

    def set(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self._expires_at = self.clock() + self.expiry

    def get(self) -> dict[str, Any] | None:
        """The pending payload, or None (clearing it if expired)."""
        if self._payload is None:
            return None
        if self.clock() >= self._expires_at:
            self.clear()
            return None
        return self._payload

    def clear(self) -> None:
        self._payload = None
        self._expires_at = 0.0
