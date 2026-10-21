"""CharacterActs: before Bro closes / minimizes / maximizes a window, the
character walks to that window's real button and presses it with a paw.

The backend finds the button on screen (OS adapter), pushes a
`character_act` event to the client, and waits until the client reports the
paw press (POST /character/done/{id}) — then the caller does the real action
through Windows (WM_CLOSE / Win+Down…), so it's reliable and the user's mouse
is never moved. No client connected / button not found / client too slow:
the action just happens without the walk.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

logger = logging.getLogger("arun.character")

ACT_TIMEOUT_SECONDS = 5.0  # walk (~1.6 s max) + reach + press, with slack
ACT_KINDS = {"close", "minimize", "maximize", "close_tab"}


class CharacterActs:
    def __init__(self, notifications, os_adapter, timeout: float = ACT_TIMEOUT_SECONDS):
        self.notifications = notifications
        self.os = os_adapter
        self.timeout = timeout
        self._waiting: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def act(self, kind: str, hwnd: int, label: str = "") -> bool:
        """Walk to `hwnd`'s `kind` button and press it; returns once pressed
        (True) or when it couldn't / didn't happen in time (False). Blocks:
        call from a worker thread, never the event loop."""
        if kind not in ACT_KINDS or self.os is None:
            return False
        point = self.os.caption_button_point(hwnd, kind)
        if point is None:
            return False
        act_id = uuid.uuid4().hex
        done = threading.Event()
        with self._lock:
            self._waiting[act_id] = done
        try:
            sent = self.notifications.broadcast_from_thread({
                "type": "character_act", "id": act_id, "kind": kind,
                "x": point[0], "y": point[1], "app": label})
            if not sent:
                return False
            pressed = done.wait(self.timeout)
            if not pressed:
                logger.info("character_act %s timed out; acting anyway", kind)
            return pressed
        finally:
            with self._lock:
                self._waiting.pop(act_id, None)

    def done(self, act_id: str) -> bool:
        """The client's paw pressed the button."""
        with self._lock:
            event = self._waiting.get(act_id)
        if event is None:
            return False
        event.set()
        return True


def act_then(character: Any, kind: str, hwnd: int | None, label: str = "") -> None:
    """Helper for callers: play the walk-and-press if a character exists."""
    if character is not None and hwnd:
        try:
            character.act(kind, hwnd, label)
        except Exception:  # an animation must never block the real action
            logger.exception("character act failed")
