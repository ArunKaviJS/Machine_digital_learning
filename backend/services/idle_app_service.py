"""Unused-app reminder: "You haven't used X for 30 min — shall I close it?"

An app counts as unused while none of its windows is in the foreground. After
idleAppMinutes of that, Bro asks once; the app is closed only after an
explicit yes, with the same polite WM_CLOSE as "close X" (the app can still
prompt to save — nothing is force-killed). One question at a time, spaced
out, never while the user is away / in DND / paused.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from backend.os_integration.helpers import app_identity

PROMPT_GAP_SECONDS = 120.0     # minimum spacing between two questions
PENDING_TTL_SECONDS = 600.0    # unanswered question -> treat as "keep it"
DEMO_THRESHOLD_SECONDS = 60.0
DEMO_PROMPT_GAP_SECONDS = 10.0


class IdleAppService:
    def __init__(self, config: dict[str, Any], os_adapter,
                 is_paused: Callable[[], bool] = lambda: False,
                 clock: Callable[[], float] = time.time):
        self.config = config
        self.os = os_adapter
        self.is_paused = is_paused
        self.clock = clock
        self._apps: dict[str, dict[str, Any]] = {}  # key -> {name, last_active}
        self._kept: set[str] = set()                # "keep it" while it stays open
        self._pending: dict[str, Any] | None = None
        self._last_prompt = float("-inf")

    # -- config ----------------------------------------------------------
    @property
    def threshold_seconds(self) -> float:
        if self.config.get("demoMode"):
            return DEMO_THRESHOLD_SECONDS
        return float(self.config.get("idleAppMinutes", 30)) * 60

    @property
    def prompt_gap_seconds(self) -> float:
        return DEMO_PROMPT_GAP_SECONDS if self.config.get("demoMode") else PROMPT_GAP_SECONDS

    def _ignored(self, window: dict) -> bool:
        ignore = {p.lower() for p in self.config.get("idleAppIgnore", [])}
        return (window.get("process_name") or "").lower() in ignore

    def _blocked(self) -> bool:
        if self.is_paused() or self.os.is_dnd_active():
            return True
        idle_limit = float(self.config.get("idleThresholdSeconds", 120))
        return self.os.get_idle_seconds() >= idle_limit

    # -- the tick ----------------------------------------------------------
    def tick(self) -> list[dict[str, Any]]:
        now = self.clock()
        events: list[dict[str, Any]] = []

        running: dict[str, str] = {}
        for win in self.os.list_windows():
            if not self._ignored(win):
                key, name = app_identity(win)
                running.setdefault(key, name)

        for key in list(self._apps):            # forget apps that were closed
            if key not in running:
                del self._apps[key]
                self._kept.discard(key)
                if self._pending and self._pending["key"] == key:
                    self._pending = None
                    events.append({"type": "idle_app_cleared", "key": key})
        for key, name in running.items():       # first sighting starts the clock
            self._apps.setdefault(key, {"name": name, "last_active": now})

        fg = self.os.get_foreground_window()
        if fg:
            key = app_identity(fg)[0]
            if key in self._apps:
                self._apps[key]["last_active"] = now
                if self._pending and self._pending["key"] == key:
                    self._pending = None        # they went back to it: question moot
                    events.append({"type": "idle_app_cleared", "key": key})

        if self._pending and now - self._pending["asked_at"] > PENDING_TTL_SECONDS:
            self._kept.add(self._pending["key"])  # ignored question = keep it
            events.append({"type": "idle_app_cleared", "key": self._pending["key"]})
            self._pending = None

        if (self._pending or self._blocked()
                or now - self._last_prompt < self.prompt_gap_seconds):
            return events

        candidates = [(now - app["last_active"], key) for key, app in self._apps.items()
                      if key not in self._kept
                      and now - app["last_active"] >= self.threshold_seconds]
        if not candidates:
            return events
        unused, key = max(candidates)
        self._pending = {"key": key, "asked_at": now}
        self._last_prompt = now
        events.append({"type": "idle_app", "key": key, "name": self._apps[key]["name"],
                       "minutes": int(unused // 60)})
        return events

    # -- the user's answer -------------------------------------------------
    def answer(self, key: str, close: bool) -> dict[str, Any]:
        if self._pending and self._pending["key"] == key:
            self._pending = None
        app = self._apps.get(key)
        if app is None:
            return {"text": "That app is already closed, bro.", "animation": "smile"}
        name = app["name"]
        if not close:
            self._kept.add(key)
            return {"text": f"Okay, I'll leave {name} open, bro.", "animation": "smile"}
        closed = sum(1 for win in self.os.list_windows()
                     if app_identity(win)[0] == key and self.os.close_window(win["hwnd"]))
        if closed:
            return {"text": f"Closing {name}, bro. If there's unsaved work, "
                            f"it'll ask you first.", "animation": "happy"}
        return {"text": f"Couldn't close {name}, bro.", "animation": "warn"}
