"""Shared pieces of the multi-agent system.

AgentSpec    what a sub-agent IS: name, role (told to the model) and its tool
             whitelist (the model can't even name another agent's tools).
AgentReply   what every sub-agent returns to the main agent.
AgentContext the app services a sub-agent may use (built per request from
             app.state, so tests that swap app.state.agent see the new one).
SubAgent     base class: `claim` = instant rule-based handling (no model
             call, no lag), `score` = how well a request fits this agent's
             domain (main agent routing), `work` = the think -> act -> observe
             loop with this agent's own prompt and tools.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.router.emotes import apply_mood


_REFERS_BACK = re.compile(r"\b(?:it|that|this|them|there|again|same|also|more)\b")


def refers_back(session, text: str) -> bool:
    """"close it", "do that again": needs the conversation, not a rule."""
    return bool(session is not None and session.user_texts
                and _REFERS_BACK.search(text.lower()))


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role: str
    tools: frozenset[str] | None  # None = every tool (general agent)


@dataclass
class AgentReply:
    text: str
    animation: str = "idle"
    status: str = "done"                     # done | question | stuck
    steps: list[dict[str, Any]] = field(default_factory=list)
    motion: str | None = None
    agent: str = ""                          # which sub-agent answered


@dataclass
class AgentContext:
    config: dict[str, Any]
    engine: Any                              # AgentService: the shared loop engine
    db: Any = None
    gateway: Any = None
    pending: Any = None
    tidy: Any = None
    os_adapter: Any = None
    character: Any = None

    @classmethod
    def from_state(cls, state: Any) -> "AgentContext":
        return cls(config=state.config, engine=getattr(state, "agent", None),
                   db=getattr(state, "db", None), gateway=getattr(state, "ai_gateway", None),
                   pending=getattr(state, "pending", None),
                   tidy=getattr(state, "tidy_service", None),
                   os_adapter=getattr(state, "os_adapter", None),
                   character=getattr(state, "character", None))


def reply_from_envelope(result: dict[str, Any], name: str, text: str,
                        mood: bool = True) -> AgentReply:
    data = result.get("data") or {}
    animation = result.get("animation") or "idle"
    return AgentReply(text=result["text"],
                      animation=apply_mood(text, animation) if mood else animation,
                      status=data.get("status", "done"),
                      steps=data.get("agent_steps", []), motion=data.get("motion"),
                      agent=name)


class SubAgent:
    spec: AgentSpec
    domain: re.Pattern | None = None         # words that mean "this is my job"

    @property
    def name(self) -> str:
        return self.spec.name

    def claim(self, session, text: str, ctx: AgentContext) -> AgentReply | None:
        """Instant handling by rules (no model). None = not mine / needs thinking."""
        return None

    def score(self, text: str) -> int:
        """How many of this agent's domain words the request contains."""
        return len(self.domain.findall(text.lower())) if self.domain is not None else 0

    def work(self, session, text: str, ctx: AgentContext) -> AgentReply | None:
        """Think -> act -> observe with this agent's prompt and tools."""
        result = ctx.engine.turn(session, text, self.spec)
        return None if result is None else reply_from_envelope(result, self.name, text)
