"""MainAgent: gets every user message and assigns it to ONE sub-agent.

  1. An answer to a sub-agent's question goes back to that same sub-agent.
  2. Instant claims, no model call (fixed priority): companion (emotes),
     writer ("write X [in app]", "open a new tab", "make it bold"), window
     ("open notepad", "close it", "minimize the window"), system ("how much
     RAM", "check my battery"), stats (usage / water / tidy rules).
  3. Otherwise pick a thinking sub-agent by domain words (instant):
     companion / writer / window / system; "open X and write…" -> writer,
     "open cmd and…" -> system; several areas -> general.
  4. No domain words at all: one tiny "which agent?" model call
     (ai/llm.py `choose`, same warm model as the agents) — else general.

Isolation: each sub-agent thinks with its own prompt and tool whitelist,
one message is handled by one sub-agent at a time (the chat's lock), the
model is single-flight (ai/llm.py), and a crash inside a sub-agent becomes
a friendly reply instead of breaking the chat.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.agents.base import AgentContext, AgentReply, SubAgent, refers_back
from backend.agents.companion_agent import CompanionAgent
from backend.agents.general_agent import GeneralAgent
from backend.agents.stats_agent import StatsAgent
from backend.agents.system_agent import SystemAgent
from backend.agents.window_agent import WindowAgent
from backend.agents.writer_agent import WriterAgent

logger = logging.getLogger("arun.agents")

NOT_UNDERSTOOD = "I didn't get that, bro. Can you say it another way?"
AI_DOWN = ("My brain (Ollama) isn't running, bro, so I can't do that right now. "
           "Start Ollama, then send it again — I still remember this chat.")
AGENT_FAILED = "Something went wrong on my side, bro. Try that once more?"

CLAIM_ORDER = ("companion", "writer", "window", "system", "stats")  # instant, no model
THINKERS = ("companion", "writer", "window", "system")      # model loop, own tools
# two areas where one specialist can do both parts
PAIRS = {frozenset({"window", "writer"}): "writer",   # "open notepad and write hi"
         frozenset({"window", "system"}): "system"}   # "open cmd and check the config"

ROUTER_QUESTION = (
    "Pick the assistant for this request.\n"
    "companion = chat, jokes, feelings, general knowledge questions\n"
    "writer = type text or do things inside an app (new tab, bold, save)\n"
    "window = open, close, switch, minimize, maximize apps or websites\n"
    "system = questions about this PC, cmd commands, Windows features, settings\n"
    "general = several of these together, or none fits\n"
    "Request: {text}")


class MainAgent:
    def __init__(self, ctx: AgentContext):
        self.ctx = ctx
        self.agents: dict[str, SubAgent] = {
            a.name: a for a in (CompanionAgent(), WriterAgent(), WindowAgent(),
                                SystemAgent(), StatsAgent(), GeneralAgent())}

    @property
    def enabled(self) -> bool:
        return self.ctx.engine is not None and self.ctx.engine.enabled

    # ---- chat: one message of a conversation ----
    def handle(self, session, text: str) -> AgentReply:
        text = text.strip()
        try:
            reply = self._dispatch(session, text)
        except Exception:  # one sub-agent's bug must not break the chat
            logger.exception("sub-agent failed on %r", text)
            session.add_reply(AGENT_FAILED)
            return AgentReply(text=AGENT_FAILED, animation="confused", agent="main")
        if reply is None:
            reply = self._no_reply(session)
        if reply.agent and reply.agent != "main":
            session.last_agent = reply.agent
        return reply

    def _dispatch(self, session, text: str) -> AgentReply | None:
        if session.awaiting_answer:  # the answer goes to whoever asked
            asker = self.agents.get(session.last_agent or "", self.agents["general"])
            return asker.work(session, text, self.ctx)
        for name in CLAIM_ORDER:
            reply = self.agents[name].claim(session, text, self.ctx)
            if reply is not None:
                return reply
        name = self.route(text, session)
        logger.info("main agent: %r -> %s", text, name)
        return self.agents[name].work(session, text, self.ctx)

    # ---- /ask: one message, no conversation ----
    def run(self, text: str) -> dict[str, Any] | None:
        """Same routing for the one-shot Ask box (QuestionRouter calls this)."""
        if not self.enabled:
            return None
        name = self.route(text, None)
        return self.ctx.engine.run(text, self.agents[name].spec if name != "general" else None)

    # ---- routing ----
    def route(self, text: str, session) -> str:
        """Which thinking sub-agent fits? Instant word matching first."""
        if refers_back(session, text) and session.last_agent in THINKERS:
            return session.last_agent  # "do that again": whoever did "that"
        hits = {name for name in THINKERS if self.agents[name].score(text) > 0}
        if len(hits) > 1:
            hits.discard("companion")  # "hey, open notepad": the job beats the greeting
        if len(hits) == 1:
            return hits.pop()
        if frozenset(hits) in PAIRS:
            return PAIRS[frozenset(hits)]
        if hits:
            return "general"
        return self._ask_model(text)

    def _ask_model(self, text: str) -> str:
        llm = getattr(self.ctx.engine, "client", None)
        choose = getattr(llm, "choose", None)
        if choose is None:
            return "general"
        pick = choose(ROUTER_QUESTION.format(text=text[:300]), [*THINKERS, "general"])
        return pick or "general"

    def _no_reply(self, session) -> AgentReply:
        """The sub-agent produced nothing: usually the model is down."""
        ping = getattr(getattr(self.ctx.engine, "client", None), "ping", None)
        text = AI_DOWN if ping is not None and not ping() else NOT_UNDERSTOOD
        session.add_reply(text)
        return AgentReply(text=text, animation="confused", agent="main")
