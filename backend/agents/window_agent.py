"""WindowAgent: apps and windows — open, close, switch, minimize, maximize
(the cat walks to the real button), websites. Clear commands ("open
notepad", "close it", "minimize the window") run instantly by rules; vaguer
ones think with the window tools."""

from __future__ import annotations

import re
from typing import Any

from backend.agents.base import AgentContext, AgentReply, AgentSpec, SubAgent, refers_back
from backend.router.intent import validate_intent
from backend.router.rules import match_rules
from backend.services.agent_service import needs_agent, window_command

_DOMAIN = re.compile(
    r"\b(?:open|launch|start|close|quit|exit|kill|minimi[sz]e|maximi[sz]e|restore|switch to|"
    r"bring up|focus|window|app|website|site|go to|\w+\.(?:com|org|net|in|io))\b")


class WindowAgent(SubAgent):
    spec = AgentSpec(
        name="window",
        role="open, close, switch, minimize and maximize apps and windows, and open "
             "websites. Close only what the user named.",
        tools=frozenset({"open_app", "close_app", "focus_window", "list_windows",
                         "windows_shortcut", "open_website", "wait", "ask_user"}))
    domain = _DOMAIN

    def claim(self, session, text: str, ctx: AgentContext) -> AgentReply | None:
        if session.awaiting_answer:
            return None
        if window_command(text):  # "minimize the window", "close it", "close this tab"
            result = ctx.engine._window_job(session, text)
            if result is not None:
                data = result["data"]
                return AgentReply(text=result["text"], animation=result["animation"],
                                  steps=data["agent_steps"], agent=self.name)
        if needs_agent(text) or refers_back(session, text):
            return None
        command = _app_command(text, ctx.config)
        if command is None:
            return None
        action, target = command  # "open notepad": instant, and remembered
        ok, observation, _ = session.tools.run(action, target)
        reply = _app_reply(ok, observation)
        session.add_tool_exchange(text, [(action, target, observation)], reply)
        return AgentReply(text=reply, animation="success" if ok else "warn",
                          steps=[{"action": action, "input": target, "ok": ok,
                                  "observation": observation}], agent=self.name)


def _app_command(text: str, config: dict[str, Any]) -> tuple[str, str] | None:
    """("open_app" | "close_app", target) when the rules are sure."""
    intent = validate_intent(match_rules(text, config), config)
    if intent and intent["intent"] in ("open_app", "close_app") and intent.get("target"):
        return intent["intent"], intent["target"]
    return None


def _app_reply(ok: bool, observation: str) -> str:
    if ok and observation.endswith(" It is in front now."):
        return observation.replace(" It is in front now.", "") + " What should I do in it, bro?"
    return observation
