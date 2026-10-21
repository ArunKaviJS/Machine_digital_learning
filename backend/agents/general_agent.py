"""GeneralAgent: the fallback for jobs that span several areas ("open
notepad, write hi, then check my battery") or that no specialist claims.
It has every tool and the full prompt (slower, but can do anything the
others can)."""

from __future__ import annotations

from backend.agents.base import AgentContext, AgentReply, AgentSpec, SubAgent, reply_from_envelope


class GeneralAgent(SubAgent):
    spec = AgentSpec(name="general", role="", tools=None)

    def work(self, session, text: str, ctx: AgentContext) -> AgentReply | None:
        result = ctx.engine.turn(session, text, None)  # None = every tool
        return None if result is None else reply_from_envelope(result, self.name, text)
