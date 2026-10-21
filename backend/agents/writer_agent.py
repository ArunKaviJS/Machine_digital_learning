"""WriterAgent: work INSIDE apps — type the user's exact words, and in-app
actions (new tab, bold, save, find...). Plain "write X [in APP]" is handled
instantly by code (the small model asked "what should I write?" or
rephrased the text); anything else ("write a note…", "open chrome, new tab,
type youtube") thinks with the writer's own tools."""

from __future__ import annotations

import re
from typing import Any

from ai.tool_catalog import actions_for, app_for_process
from backend.agents.base import AgentContext, AgentReply, AgentSpec, SubAgent
from backend.services.agent_service import parse_write_request
from backend.services.app_launcher_service import APP_ALIASES, AppLauncherService, best_app_match

WHICH_APP = "Which app should I write it in, bro? (e.g. \"notepad\")"
# one-word actions clear enough to do straight away ("find", "new", "print"
# are too vague alone: "find my files" isn't Ctrl+F)
SINGLE_WORD_ACTIONS = {"bold", "italic", "underline", "undo", "redo", "refresh", "save",
                       "copy", "paste", "cut"}
_ANSWER_LEAD = re.compile(r"^(?:(?:in|into|on|open|use|the|a|my|new)\s+)+", re.I)
_DOMAIN = re.compile(
    r"\b(?:write|type|draft|jot|note down|paste|copy|new tab|close tab|bold|italic|underline|"
    r"save|find|replace|select all|undo|redo|refresh|reload|zoom|font|align\w*|bullet|"
    r"new slide|slideshow|autosum|new folder|rename|address bar|scroll)\b")


class WriterAgent(SubAgent):
    spec = AgentSpec(
        name="writer",
        role="work inside apps: type the user's exact words, and use the app's own "
             "actions (new tab, bold, save, find). Open or focus the app first if needed.",
        tools=frozenset({"open_app", "focus_window", "type_text", "press_key", "app_actions",
                         "app_action", "list_windows", "wait", "ask_user"}))
    domain = _DOMAIN

    def claim(self, session, text: str, ctx: AgentContext) -> AgentReply | None:
        if session.awaiting_answer:
            return None
        return self._write(session, text) or self._direct_action(session, text)

    def _direct_action(self, session, text: str) -> AgentReply | None:
        """"open a new tab", "make it bold", "undo": the request names exactly
        one action of the app in front -> do it (live, the model spent two
        steps / 14 s observing first)."""
        words = set(re.findall(r"[a-z]+", text.lower()))
        if (len(words) > 7 or words & {"and", "then", "after", "write", "type"}
                or "\n" in text):
            return None
        tools = session.tools
        target = tools._app_target()
        if target is None:
            return None
        actions = actions_for(app_for_process(target.get("process_name")))
        matches = [name for name in actions
                   if all(w in words for w in name.split("_"))
                   and ("_" in name or name in SINGLE_WORD_ACTIONS)]
        if not matches:
            return None
        best = max(len(name.split("_")) for name in matches)
        top = [name for name in matches if len(name.split("_")) == best]
        if len(top) != 1:
            return None  # ambiguous: let the model think
        ok, observation, _ = tools.run("app_action", top[0])
        reply = f"Done, bro — {observation}" if ok else observation
        session.add_tool_exchange(text, [("app_action", top[0], observation)], reply)
        return AgentReply(text=reply, animation="success" if ok else "warn", agent=self.name,
                          steps=[{"action": "app_action", "input": top[0], "ok": ok,
                                  "observation": observation}])

    def _write(self, session, text: str) -> AgentReply | None:
        """Plain "write X [in APP]" (or the app answering our "which app?"):
        open/reuse the app and type X exactly as written."""
        tools = session.tools
        if session.pending_write is not None:       # answer to "which app?"
            body, app_name = session.pending_write, _ANSWER_LEAD.sub("", text).strip(" .!?")
            session.pending_write = None
            if not _known_app(tools, app_name):
                return None                         # not an app: a new request
        else:
            parsed = parse_write_request(text)
            if parsed is None:
                return None
            body, app_name, full = parsed
            if app_name and not _known_app(tools, app_name):
                body, app_name = full, None         # "write meet me in the morning"

        steps: list[tuple[str, str, str]] = []
        reported: list[dict[str, Any]] = []

        def run(action: str, arg: str) -> bool:
            ok, observation, _ = tools.run(action, arg)
            steps.append((action, arg, observation))
            reported.append({"action": action, "input": arg, "ok": ok,
                             "observation": observation})
            return ok

        active = tools._alive(tools.active)
        if app_name:
            if (not (active and tools._match_score(app_name, active) > 0)
                    and not run("open_app", app_name)):
                return self._finish(session, text, steps, reported, steps[-1][2], "warn")
        elif active is None:                        # nothing opened in this chat yet
            session.pending_write = body
            session.add_tool_exchange(text, [], WHICH_APP)
            return AgentReply(text=WHICH_APP, animation="thinking", status="question",
                              agent=self.name)
        if not run("type_text", body):
            return self._finish(session, text, steps, reported, steps[-1][2], "warn")
        where = tools._name(tools.active) if tools.active else "the app"
        return self._finish(session, text, steps, reported,
                            f"Wrote \"{body}\" in {where}, bro.", "success")

    def _finish(self, session, text, steps, reported, reply, animation) -> AgentReply:
        session.add_tool_exchange(text, steps, reply)
        return AgentReply(text=reply, animation=animation, steps=reported, agent=self.name)


def _known_app(tools, name: str) -> bool:
    """An installed or open app (so "in the morning" isn't taken as one)."""
    if not name:
        return False
    if tools._find_window(name) is not None:
        return True
    query = APP_ALIASES.get(name.lower().strip(), name)
    return best_app_match(query, AppLauncherService(tools.os).installed_apps()) is not None
