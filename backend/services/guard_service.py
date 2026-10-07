"""Distraction guard state machine (SKILL §15).

IDLE -> TRACKING (streak builds) -> NAGGING -> COUNTDOWN -> CLOSING -> COOLDOWN.
Streak = accumulated seconds on a tracked site since a break of >= breakReset.
Mandatory safety before Ctrl+W: re-read the foreground window and close only
if it is still the same browser+site (and DND is off).
Demo mode swaps in short timings from DEMO_TIMINGS.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import math
import os
import time
from typing import Any, Callable

from backend.db.connection import Database
from backend.db.repositories.guard_repo import GuardRepo
from backend.os_integration.helpers import classify, is_browser, is_dnd_app

logger = logging.getLogger("arun.guard")

# demoMode=true: nag 10 s, countdown from 20 s, close at 30 s (20 + warning),
# repeat every 5 s, break reset 30 s (SKILL §15)
DEMO_TIMINGS = {"nag_after": 10.0, "close_after": 20.0, "warning": 10.0,
                "nag_repeat": 5.0, "break_reset": 30.0}

IDLE, TRACKING, NAGGING, COUNTDOWN, CLOSING, COOLDOWN = (
    "IDLE", "TRACKING", "NAGGING", "COUNTDOWN", "CLOSING", "COOLDOWN")


class GuardService:
    def __init__(self, db: Database, config: dict[str, Any], os_adapter,
                 clock: Callable[[], float] = time.time,
                 notifications=None):
        self.repo = GuardRepo(db)
        self.config = config
        self.adapter = os_adapter
        self.clock = clock
        self.notifications = notifications  # NotificationManager or None
        self.state = IDLE
        self.site: str | None = None
        self.streak = float(self.repo.get_streak())
        self.away = 0.0
        self._last_tick: float | None = None
        self._nag_last = 0.0
        self._countdown_started = 0.0
        self._cooldown_until = 0.0

    # -- config ----------------------------------------------------------
    def _timings(self) -> dict[str, float]:
        if self.config.get("demoMode"):
            return dict(DEMO_TIMINGS)
        c = self.config
        return {
            "nag_after": float(c.get("nagAfterMinutes", 15)) * 60,
            "close_after": float(c.get("closeAfterMinutes", 25)) * 60,
            "warning": float(c.get("warningSeconds", 60)),
            "nag_repeat": float(c.get("nagRepeatSeconds", 120)),
            "break_reset": float(c.get("breakResetMinutes", 10)) * 60,
        }

    def snapshot(self) -> dict[str, Any]:
        return self.get_status()

    def get_status(self) -> dict[str, Any]:
        seconds_left = 0
        if self.state == COUNTDOWN:
            t = self._timings()
            remaining = t["warning"] - (self.clock() - self._countdown_started)
            seconds_left = max(0, int(math.ceil(remaining)))
        return {
            "state": self.state,
            "site": self.site,
            "streak_seconds": int(self.streak),
            "seconds_left": seconds_left,
            "paused": self.is_paused(),
        }

    def is_paused(self) -> bool:
        from backend.db.connection import get_meta
        return get_meta(self.repo.db, "guard.paused", "false") == "true"

    def pause(self) -> dict[str, Any]:
        from backend.db.connection import set_meta
        set_meta(self.repo.db, "guard.paused", "true")
        logger.info("guard manual pause enabled")
        return {"paused": True, "status": self.get_status()}

    def resume(self) -> dict[str, Any]:
        from backend.db.connection import set_meta
        set_meta(self.repo.db, "guard.paused", "false")
        logger.info("guard manual pause disabled (resumed)")
        return {"paused": False, "status": self.get_status()}

    def cancel(self) -> dict[str, Any]:
        site = self.site
        self._log("cancelled", site)
        self._reset_streak()
        self.state = IDLE
        logger.info("guard cancelled (site=%s)", site)
        return {"type": "cancelled", "site": site, "status": self.get_status()}

    # -- helpers ---------------------------------------------------------
    def _now_iso(self) -> tuple[str, str]:
        dt = datetime.datetime.fromtimestamp(self.clock()).astimezone()
        return dt.isoformat(timespec="seconds"), dt.date().isoformat()

    def _log(self, type_: str, site: str | None) -> None:
        ts, date = self._now_iso()
        self.repo.add_event(ts, date, type_, site)

    def _classify_fg(self, fg: dict | None) -> str | None:
        if not fg:
            return None
        return classify(fg.get("process_name"), fg.get("title"),
                        self.config.get("browsers", []),
                        self.config.get("siteMatchers", {}))

    def _suppressed(self, fg: dict | None, idle_too_long: bool) -> bool:
        if self.is_paused():
            return True
        if idle_too_long or self.adapter.is_dnd_active():
            return True
        return bool(fg) and is_dnd_app(fg.get("process_name"),
                                       self.config.get("dndApps", []))

    def _reset_streak(self) -> None:
        self.streak = 0.0
        self.state = IDLE
        self.site = None
        _, date = self._now_iso()
        self.repo.set_streak(0, date)

    # -- the tick --------------------------------------------------------
    def tick(self) -> list[dict[str, Any]]:
        """One poll: accrue streak/away, advance the machine, emit events."""
        now = self.clock()
        delta = 0.0
        if self._last_tick is not None:
            max_gap = float(self.config.get("maxGapSeconds", 120))
            delta = max(0.0, min(now - self._last_tick, max_gap))
        self._last_tick = now

        fg = self.adapter.get_foreground_window()
        if fg and fg.get("pid") == os.getpid() and self.state != COUNTDOWN:
            return []  # Arun's own window: keep previous state (D11)

        idle_too_long = self.adapter.get_idle_seconds() >= float(
            self.config.get("idleThresholdSeconds", 120))
        site = self._classify_fg(fg)
        t = self._timings()

        # -- streak / away accounting ------------------------------------
        if site and not idle_too_long and not self.is_paused():
            self.away = 0.0
            self.streak += delta
            self.site = site
            if self.state == IDLE:
                self.state = TRACKING
            _, date = self._now_iso()
            self.repo.set_streak(int(self.streak), date)
        else:
            self.away += delta
            if self.away >= t["break_reset"] and self.state != COOLDOWN:
                self._reset_streak()

        suppressed = self._suppressed(fg, idle_too_long)
        events: list[dict[str, Any]] = []

        # -- state machine ------------------------------------------------
        if self.state == COOLDOWN:
            if now >= self._cooldown_until:
                self.state = IDLE
            return events

        if self.state == COUNTDOWN:
            self._step_countdown(now, fg, suppressed, events)
            return events

        if self.state == NAGGING:
            if not site:
                self.state = TRACKING  # paused; streak kept, break-reset handles leaving
            else:
                if not suppressed and now - self._nag_last >= t["nag_repeat"]:
                    self._emit_nag(events)
                if not suppressed and self.streak >= t["close_after"]:
                    self.state = COUNTDOWN
                    self._countdown_started = now
                    self._log("countdown_start", self.site)
                    events.append({"type": "countdown_start", "site": self.site,
                                   "seconds_left": int(t["warning"])})
            return events

        # IDLE / TRACKING
        if site and not suppressed and self.streak >= t["nag_after"] \
                and self.state in (IDLE, TRACKING):
            self.state = NAGGING
            self._emit_nag(events)
        return events

    def _emit_nag(self, events: list[dict]) -> None:
        self._nag_last = self.clock()
        self._log("nag", self.site)
        events.append({"type": "nag", "site": self.site,
                       "streak_seconds": int(self.streak)})

    def _step_countdown(self, now: float, fg: dict | None,
                        suppressed: bool, events: list[dict]) -> None:
        t = self._timings()
        remaining = t["warning"] - (now - self._countdown_started)
        if remaining > 0:
            events.append({"type": "countdown_tick", "site": self.site,
                           "seconds_left": int(math.ceil(remaining))})
            return

        # expiry: MANDATORY safety re-read (fresh foreground + DND) — SKILL §15
        fresh_fg = self.adapter.get_foreground_window()
        fresh_site = self._classify_fg(fresh_fg)
        safe = (
            fresh_fg is not None
            and fresh_fg.get("pid") != os.getpid()
            and fresh_site == self.site
            and is_browser(fresh_fg.get("process_name"),
                           self.config.get("browsers", []))
            and not self._suppressed(fresh_fg, False)
        )
        closed = False
        if safe:
            closed = self.adapter.send_close_tab()
        if closed:
            self._log("tab_closed", self.site)
            events.append({"type": "tab_closed", "site": self.site})
        else:
            reason = "foreground_changed" if fresh_site != self.site else "blocked"
            self._log("cancelled", self.site)
            events.append({"type": "cancelled", "site": self.site,
                           "reason": reason})
        site_closed = self.site
        self._reset_streak()
        self.state = COOLDOWN
        self._cooldown_until = now + t["break_reset"]
        logger.info("guard closed=%s site=%s", closed, site_closed)

    # -- client actions --------------------------------------------------
    def snooze(self, seconds: float = 300.0) -> dict[str, Any]:
        """[5 more min] from the countdown popup: pause the machine."""
        site = self.site
        self._log("snoozed", site)
        self._reset_streak()
        self.state = COOLDOWN
        self._cooldown_until = self.clock() + seconds
        return {"type": "snoozed", "site": site,
                "until": datetime.datetime.fromtimestamp(self._cooldown_until)
                             .astimezone().isoformat(timespec="seconds")}

    # -- loop ------------------------------------------------------------
    async def run(self) -> None:
        poll = float(self.config.get("pollSeconds", 2))
        logger.info("guard loop started (poll=%ss)", poll)
        while True:
            await asyncio.sleep(poll)
            try:
                for payload in self.tick():
                    if self.notifications is not None:
                        await self.notifications.broadcast(payload)
            except asyncio.CancelledError:
                logger.info("guard loop stopped")
                raise
            except Exception:
                logger.exception("guard tick failed")
