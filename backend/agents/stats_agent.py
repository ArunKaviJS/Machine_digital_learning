"""StatsAgent: the user's own data — YouTube / screen time, top app, water,
tidy, and the other quick rules. Answers from the database through the
rule router (+ the intent model only if the rules aren't sure); it never
runs the think/act loop, so it's fast."""

from __future__ import annotations

from backend.agents.base import AgentContext, AgentReply, AgentSpec, SubAgent, refers_back
from backend.router.emotes import mood_animation
from backend.router.router import CLARIFICATION, QuestionRouter
from backend.services.agent_service import needs_agent, window_command


class StatsAgent(SubAgent):
    spec = AgentSpec(name="stats", role="answer from the user's own usage/water/tidy data",
                     tools=frozenset())

    def claim(self, session, text: str, ctx: AgentContext) -> AgentReply | None:
        if (session.awaiting_answer or needs_agent(text) or window_command(text)
                or mood_animation(text) is not None  # small talk: the companion's job
                or refers_back(session, text)):
            return None
        result = QuestionRouter(
            db=ctx.db, config=ctx.config, ai_gateway=ctx.gateway, pending=ctx.pending,
            tidy_service=ctx.tidy, os_adapter=ctx.os_adapter, character=ctx.character,
        ).ask(text)
        if result["text"] == CLARIFICATION:
            return None
        session.add_exchange(text, result["text"])
        return AgentReply(text=result["text"], animation=result["animation"],
                          motion=(result.get("data") or {}).get("motion"), agent=self.name)

    def work(self, session, text: str, ctx: AgentContext) -> AgentReply | None:
        return None  # rules only
