"""QuestionRouter: pending yes/no → rules → execute → AI fallback → clarify.

Services are built per call from the injected db/config so the router is
stateless apart from the shared PendingConfirmation store (SKILL §7, §10).
"""

from __future__ import annotations

import datetime
import time
from typing import Any, Callable

from backend.router.confirmations import PendingConfirmation
from backend.router.intent import validate_intent
from backend.router.rules import match_rules, normalise
from backend.router.templates import fmt_clock, period_label, render_intent
from backend.services.stats_service import StatsService
from backend.services.usage_service import UsageService

YES_WORDS = {"yes", "yep", "yeah", "yup", "ok", "okay", "sure", "confirm",
             "do it", "go ahead", "y"}
NO_WORDS = {"no", "nope", "cancel", "stop", "never mind", "nevermind", "n"}

CLARIFICATION = ("I couldn't understand that, bro. Try a Quick Question "
                 "from my menu.")

BASELINE_LABELS = {"average": "your usual average", "yesterday": "yesterday",
                   "last_week": "the same days last week", "none": None}


class QuestionRouter:
    def __init__(self, db, config, ai_gateway=None,
                 pending: PendingConfirmation | None = None,
                 tidy_service=None, os_adapter=None,
                 clock: Callable[[], float] = time.time,
                 today_fn: Callable[[], datetime.date] = datetime.date.today):
        self.db = db
        self.config = config
        self.ai_gateway = ai_gateway
        self.pending = pending or PendingConfirmation(clock=clock)
        self.tidy = tidy_service
        self.os_adapter = os_adapter
        self.clock = clock
        self.today_fn = today_fn

    # -- public ----------------------------------------------------------
    def ask(self, text: str) -> dict[str, Any]:
        norm = normalise(text)

        # step 1: pending confirmation (yes/no words only mean something here)
        if norm:
            payload = self.pending.get()
            if payload is not None:
                if norm in YES_WORDS or norm.startswith("yes "):
                    return self._confirm_pending(payload)
                if norm in NO_WORDS or norm.startswith("no "):
                    self.pending.clear()
                    return _envelope("No problem, bro — cancelled.", "smile")

        # step 2: rule-based router
        intent = validate_intent(match_rules(text, self.config), self.config)

        # step 3: AI gateway (M7) when rules had no confident answer
        if intent is None and self.ai_gateway is not None:
            intent = validate_intent(self.ai_gateway.parse_intent(text),
                                     self.config)

        # step 4: execute, or ask the user to use a Quick Question
        if intent is None:
            return _envelope(CLARIFICATION, "idle")
        return self.execute(intent)

    def execute(self, intent: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_do_{intent['intent']}", None)
        if handler is None:
            return _envelope(CLARIFICATION, "idle")
        return _wrap(handler(intent))

    # -- pending ---------------------------------------------------------
    def _confirm_pending(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.pending.clear()
        if payload.get("kind") == "tidy" and self.tidy is not None:
            result = self.tidy.confirm(payload["proposal_id"])
            return _envelope(result["text"], result.get("animation", "happy"))
        return _envelope("Done, bro.", "happy")

    # -- helpers ---------------------------------------------------------
    def _usage_service(self) -> UsageService:
        return UsageService(self.db, self.today_fn)

    def _stats_service(self) -> StatsService:
        return StatsService(self.db, self.today_fn)

    def _site_label(self, site: str | None) -> str:
        if site is None or site == "any":
            return "everything"
        keywords = self.config.get("siteMatchers", {}).get(site, [])
        return keywords[0] if keywords else site

    def _label(self, period: str | None) -> str:
        return period_label(period)

    # -- intent handlers -------------------------------------------------
    def _do_usage_query(self, intent: dict) -> tuple[str, str]:
        site = None if intent["application"] == "any" else intent["application"]
        row = self._usage_service().usage(intent["period"], site=site)
        data = {"seconds": row["seconds"],
                "site_label": self._site_label(site),
                "period_label": self._label(intent["period"])}
        return render_intent(intent, data)

    def _do_screen_time(self, intent: dict) -> tuple[str, str]:
        row = self._usage_service().screen_time(intent["period"])
        data = {"seconds": row["seconds"],
                "period_label": self._label(intent["period"])}
        return render_intent(intent, data)

    def _do_top_app(self, intent: dict) -> tuple[str, str]:
        row = self._usage_service().top_app(intent["period"])
        data = {"application": row["application"] if row else None,
                "seconds": row["seconds"] if row else None,
                "period_label": self._label(intent["period"])}
        return render_intent(intent, data)

    def _do_longest_session(self, intent: dict) -> tuple[str, str]:
        row = self._usage_service().longest_session(intent["period"])
        if row is None:
            data = {"seconds": None, "application": None,
                    "period_label": self._label(intent["period"])}
        else:
            data = {"seconds": row["seconds"], "application": row["application"],
                    "site_label": self._site_label(row["website"]) if row["website"] else None,
                    "period_label": self._label(intent["period"])}
        return render_intent(intent, data)

    def _do_most_active_hour(self, intent: dict) -> tuple[str, str]:
        row = self._usage_service().most_active_hour(intent["period"])
        data = {"hour": row["hour"] if row else None,
                "seconds": row["seconds"] if row else 0,
                "period_label": self._label(intent["period"])}
        return render_intent(intent, data)

    def _do_compare_usage(self, intent: dict) -> tuple[str, str]:
        site = None if intent["application"] == "any" else intent["application"]
        row = self._stats_service().compare_usage(
            intent["period"], website=site, comparison=intent["comparison"])
        data = {"seconds": row["seconds"], "baseline": row["baseline"],
                "diff": row["diff"], "site_label": self._site_label(site),
                "period_label": self._label(intent["period"]),
                "baseline_label": BASELINE_LABELS[intent["comparison"]]}
        return render_intent(intent, data)

    _do_compare_days = _do_compare_usage

    def _water_service(self):
        from backend.services.water_service import WaterService
        return WaterService(self.db, self.config, today_fn=self.today_fn)

    def _do_water_status(self, intent: dict) -> tuple[str, str]:
        svc = self._water_service()
        data = {"count": svc.today_count(), "target": svc.target}
        return render_intent(intent, data)

    def _do_log_water(self, intent: dict) -> tuple[str, str]:
        data = self._water_service().drank()
        return render_intent(intent, data)

    def _do_last_water_reminder(self, intent: dict) -> tuple[str, str]:
        row = self._water_service().last_reminder()
        data = {"time": fmt_clock(row["timestamp"]) if row else None,
                "date": row["date"] if row else None}
        return render_intent(intent, data)

    def _do_tidy_folder(self, intent: dict) -> dict[str, Any]:
        if self.tidy is None:
            return _envelope("Folder tidying isn't ready yet, bro.", "idle")
        from backend.services.tidy_service import TidyError
        try:
            proposal = self.tidy.propose(intent["folder"])
        except TidyError as exc:
            return _envelope(exc.message, "warn")

        if proposal.get("needs_confirmation"):
            self.pending.set({"kind": "tidy",
                              "proposal_id": proposal["proposal_id"],
                              "folder": intent["folder"]})
        return _envelope(proposal["text"], proposal.get("animation", "idle"),
                         needs_confirmation=proposal.get("needs_confirmation", False),
                         proposal_id=proposal.get("proposal_id"))

    def _do_undo_tidy(self, intent: dict) -> dict[str, Any]:
        if self.tidy is None:
            return _envelope("Folder tidying isn't ready yet, bro.", "idle")
        from backend.services.tidy_service import TidyError
        try:
            result = self.tidy.undo()
            return _envelope(result["text"], result.get("animation", "happy"))
        except TidyError as exc:
            return _envelope(exc.message, "warn")

    # -- open / close a tracked site --------------------------------------
    def _do_open_site(self, intent: dict) -> tuple[str, str]:
        from backend.services.app_launcher_service import AppLauncherService

        site = intent["application"]
        opened = AppLauncherService().open_site(site)
        return render_intent(intent, {"site_label": self._site_label(site),
                                      "opened": opened})

    def _do_close_site_tab(self, intent: dict) -> tuple[str, str]:
        site = intent["application"]
        closed = False
        reason = "unavailable"
        if self.os_adapter is not None:
            from backend.os_integration.helpers import classify

            fg = self.os_adapter.get_foreground_window()
            fg_site = classify(fg.get("process_name"), fg.get("title"),
                               self.config.get("browsers", []),
                               self.config.get("siteMatchers", {})) if fg else None
            if fg_site == site and not self.os_adapter.is_dnd_active():
                closed = self.os_adapter.send_close_tab()
                reason = None
            else:
                reason = "not_foreground"
        return render_intent(intent, {"site_label": self._site_label(site),
                                      "closed": closed, "reason": reason})

    # -- open / close any app, open Settings pages (no admin rights) -----
    def _launcher(self):
        from backend.services.app_launcher_service import AppLauncherService
        return AppLauncherService(self.os_adapter)

    def _do_open_app(self, intent: dict) -> tuple[str, str]:
        return render_intent(intent, self._launcher().open_app(intent["target"]))

    def _do_close_app(self, intent: dict) -> tuple[str, str]:
        return render_intent(intent, self._launcher().close_app(intent["target"]))

    def _do_open_settings(self, intent: dict) -> tuple[str, str]:
        from backend.services.system_service import SystemService
        return render_intent(intent, SystemService(self.os_adapter)
                             .open_settings(intent.get("target")))


def _envelope(text: str, animation: str, needs_confirmation: bool = False,
              proposal_id: str | None = None,
              data: dict | None = None) -> dict[str, Any]:
    return {"text": text, "animation": animation,
            "needs_confirmation": needs_confirmation,
            "proposal_id": proposal_id, "data": data or {}}


def _wrap(result) -> dict[str, Any]:
    """Handlers return (text, animation) or an envelope dict."""
    if isinstance(result, dict):
        return result
    text, animation = result
    return _envelope(text, animation)
