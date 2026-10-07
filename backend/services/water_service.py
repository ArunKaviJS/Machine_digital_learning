"""WaterService (SKILL §16): drink/snooze events, daily count, reminder timing.

Reminder cadence: next due = last relevant event + waterIntervalMinutes,
except a snooze which buys exactly 10 minutes. First run: now + interval.
Timing comes from an injected clock so tests control time.
"""

from __future__ import annotations

import datetime
import time
from typing import Any, Callable

from backend.db.connection import Database, get_meta, set_meta
from backend.db.repositories.water_repo import WaterRepo

SNOOZE_SECONDS = 600  # §16: "Remind me later" = 10 min
SCHEDULER_TYPES = ("drank", "reminder_shown", "snoozed", "dismissed")


def _epoch(iso_timestamp: str) -> float:
    return datetime.datetime.fromisoformat(iso_timestamp).timestamp()


class WaterService:
    def __init__(self, db: Database, config: dict[str, Any],
                 clock: Callable[[], float] = time.time,
                 today_fn: Callable[[], datetime.date] = datetime.date.today):
        self.db = db
        self.repo = WaterRepo(db)
        self.config = config
        self.clock = clock
        self.today_fn = today_fn
        # pin the first reminder to service start (persisted; see next_due)
        self.next_due()

    @property
    def interval_seconds(self) -> float:
        return float(self.config.get("waterIntervalMinutes", 60)) * 60

    @property
    def target(self) -> int:
        return int(self.config.get("waterDailyTarget", 8))

    @property
    def snooze_seconds(self) -> float:
        return float(self.config.get("waterSnoozeMinutes", 10)) * 60

    # -- state -----------------------------------------------------------
    def today_count(self) -> int:
        return self.repo.count_drunk(self.today_fn().isoformat())

    def last_reminder(self):
        return self.repo.last_of_type("reminder_shown")

    def next_due(self) -> float:
        """Epoch time of the next allowed reminder."""
        row = self.repo.last(SCHEDULER_TYPES)
        if row is None:
            # no events yet: first reminder = one interval after the very
            # first calculation. Persisted so it does not slide with "now";
            # recomputed if it went stale (app restarted much later).
            now = self.clock()
            stored = get_meta(self.db, "water.first_due")
            if stored is None or float(stored) < now - self.interval_seconds:
                stored = str(now + self.interval_seconds)
                set_meta(self.db, "water.first_due", stored)
            return float(stored)
        if row["type"] == "snoozed":
            return _epoch(row["timestamp"]) + self.snooze_seconds
        if row["type"] == "dismissed":
            return _epoch(row["timestamp"]) + self.interval_seconds
        # drank / reminder_shown
        return _epoch(row["timestamp"]) + self.interval_seconds

    def due(self) -> bool:
        return self.clock() >= self.next_due()

    def blocked(self, os_adapter) -> bool:
        """No reminders while DND is on, paused, or the user is away (§16)."""
        from backend.db.connection import get_meta
        if get_meta(self.repo.db, "guard.paused", "false") == "true":
            return True
        if os_adapter.is_dnd_active():
            return True
        idle_limit = float(self.config.get("idleThresholdSeconds", 120))
        return os_adapter.get_idle_seconds() >= idle_limit

    # -- actions ---------------------------------------------------------
    def _now_iso(self) -> tuple[str, str]:
        dt = datetime.datetime.fromtimestamp(self.clock()).astimezone()
        return dt.isoformat(timespec="seconds"), dt.date().isoformat()

    def drank(self) -> dict[str, Any]:
        ts, date = self._now_iso()
        self.repo.add(ts, date, "drank")
        return {"count": self.today_count(), "target": self.target}

    @staticmethod
    def _iso(epoch_seconds: float) -> str:
        return datetime.datetime.fromtimestamp(epoch_seconds) \
                   .astimezone().isoformat(timespec="seconds")

    def snooze(self) -> dict[str, Any]:
        ts, date = self._now_iso()
        self.repo.add(ts, date, "snoozed")
        return {"snoozed": True, "next_due": self._iso(self.next_due())}

    def dismiss(self) -> dict[str, Any]:
        ts, date = self._now_iso()
        self.repo.add(ts, date, "dismissed")
        return {"dismissed": True, "next_due": self._iso(self.next_due())}

    def mark_reminder_shown(self) -> float:
        """Log the reminder (resets cadence); returns the new next_due."""
        ts, date = self._now_iso()
        self.repo.add(ts, date, "reminder_shown")
        return self.next_due()

    def today_summary(self) -> dict[str, Any]:
        return {"count": self.today_count(), "target": self.target,
                "next_due": datetime.datetime.fromtimestamp(self.next_due())
                                .astimezone().isoformat(timespec="seconds")}
