"""Activity tracker: poll loop + session lifecycle (SKILL §14).

Rules implemented here:
- ignore ticks where the foreground process is Arun itself (pid match)
- idle >= idleThresholdSeconds closes the current session
- (application, website) change closes the old session and opens a new one
- gaps > maxGapSeconds are clamped (sleep never counted)
- sessions are split at local midnight
- a heartbeat + the open session are persisted to meta every tick, so an
  abrupt crash is recovered on the next start (close at last heartbeat)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from backend.db.connection import Database, get_meta, set_meta
from backend.db.repositories.usage_repo import UsageRepo
from backend.os_integration.helpers import classify, friendly_app_name

logger = logging.getLogger("arun.tracker")

HEARTBEAT_KEY = "tracker.heartbeat"
OPEN_SESSION_KEY = "tracker.open_session"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _date_of(ts: float) -> str:
    return datetime.fromtimestamp(ts).astimezone().date().isoformat()


def _midnight_after(ts: float) -> float:
    local = datetime.fromtimestamp(ts).astimezone()
    nxt = (local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return nxt.timestamp()


class ActivityTracker:
    def __init__(
        self,
        db: Database,
        os_adapter: Any,
        config: dict[str, Any],
        clock: Callable[[], float] = time.time,
    ):
        self.db = db
        self.os = os_adapter
        self.cfg = config
        self.clock = clock
        self.repo = UsageRepo(db)
        self._open: dict[str, Any] | None = None
        self._last_tick: float | None = None
        self.recover()

    # ---- crash recovery ----

    def recover(self) -> None:
        """Close a dangling session from a previous run at its heartbeat."""
        raw = get_meta(self.db, OPEN_SESSION_KEY)
        if not raw:
            return
        try:
            state = json.loads(raw)
            hb_raw = get_meta(self.db, HEARTBEAT_KEY)
            try:
                heartbeat = datetime.fromisoformat(hb_raw).timestamp() if hb_raw else 0.0
            except ValueError:
                heartbeat = 0.0
            start = float(state["start"])
            last = float(state.get("last", start))
            end = max(start, min(heartbeat or last, last))
            self._write_segments(state["application"], state["website"],
                                 state.get("window_title"), start, end)
            logger.info(
                "recovered dangling session %s (%s -> %s)",
                state["application"], _iso(start), _iso(end),
            )
        except Exception as exc:
            logger.warning("recovery failed: %s", exc)
        finally:
            set_meta(self.db, OPEN_SESSION_KEY, "")

    # ---- main entry points ----

    def tick(self) -> None:
        now = self.clock()
        set_meta(self.db, HEARTBEAT_KEY, _iso(now))

        fg = self.os.get_foreground_window()

        if self._is_self(fg):
            self._last_tick = now
            return

        if fg is None:  # lock screen / no window -> treat as away
            self._close_away(now, self.os.get_idle_seconds())
            return

        idle = self.os.get_idle_seconds()
        if idle >= self.cfg["idleThresholdSeconds"]:
            self._close_away(now, idle)
            return

        # sleep / clock jump: clamp the gap, never count it
        if self._last_tick is not None and now - self._last_tick > self.cfg["maxGapSeconds"]:
            if self._open:
                self._close_session(max(self._open["start"], self._last_tick))
            self._open = None

        self._split_at_midnight(now)

        website = classify(fg.get("process_name"), fg.get("title"),
                           self.cfg["browsers"], self.cfg["siteMatchers"])
        if website is None and not self.cfg["trackAllApps"]:
            self._close_session(now)
            self._last_tick = now
            return

        application = friendly_app_name(fg.get("process_name"))
        window_title = fg.get("title") if self.cfg["storeTitles"] else None

        if self._open and self._open["application"] == application \
                and self._open["website"] == website:
            self._open["last"] = now
        else:
            self._close_session(now)
            self._open = {
                "application": application,
                "website": website,
                "window_title": window_title,
                "start": now,
                "last": now,
            }
        self._last_tick = now
        self._persist_open()

    def close(self) -> None:
        """Flush the open session (shutdown): runs until the last tick/now."""
        if not self._open:
            return
        self._close_session(max(self.clock(), self._open["last"]))

    def _close_away(self, now: float, idle: float) -> None:
        """Close because the user is away / locked: end at last input."""
        if self._open:
            end = max(self._open["start"], now - idle)
            self._close_session(end)
        self._last_tick = now

    async def run(self) -> None:
        """Background loop; every pollSeconds (SKILL §14)."""
        interval = self.cfg["pollSeconds"]
        while True:
            await asyncio.sleep(interval)
            try:
                self.tick()
            except Exception:
                logger.exception("tracker tick failed")

    # ---- internals ----

    def _is_self(self, fg: dict[str, Any] | None) -> bool:
        return bool(fg) and fg.get("pid") == os.getpid()

    def _persist_open(self) -> None:
        set_meta(self.db, OPEN_SESSION_KEY,
                 json.dumps(self._open) if self._open else "")

    def _close_session(self, end_ts: float) -> None:
        if not self._open:
            return
        state = self._open
        self._open = None
        self._persist_open()
        self._write_segments(state["application"], state["website"],
                             state["window_title"], state["start"], end_ts)

    def _write_segments(
        self, application: str, website: str | None, window_title: str | None,
        start_ts: float, end_ts: float,
    ) -> None:
        """Write the session as one row per local day (midnight split)."""
        seg_start = start_ts
        while seg_start < end_ts:
            boundary = _midnight_after(seg_start)
            seg_end = min(boundary, end_ts)
            if seg_end > seg_start:
                self.repo.insert_session(
                    application=application,
                    website=website,
                    window_title=window_title,
                    start_time=_iso(seg_start),
                    end_time=_iso(seg_end),
                    duration_seconds=int(seg_end - seg_start),
                    date=_date_of(seg_start),
                )
            seg_start = seg_end

    def _split_at_midnight(self, now: float) -> None:
        """If the open session crossed midnight, flush the part before it."""
        while self._open:
            boundary = _midnight_after(self._open["start"])
            if boundary > now:
                break
            state = self._open
            self._write_segments(state["application"], state["website"],
                                 state["window_title"], state["start"], boundary)
            state["start"] = boundary
            self._persist_open()
