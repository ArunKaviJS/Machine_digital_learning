"""CompanionAgent: Bro's personality — emotes ("dance", "come here"), small
talk, jokes, feelings and general-knowledge answers. Never touches the PC:
its only tool is `finish`."""

from __future__ import annotations

import re

from backend.agents.base import AgentContext, AgentReply, AgentSpec, SubAgent
from backend.router.emotes import match_emote, mood_animation

_CHAT = re.compile(
    r"\b(?:hi|hello|hey|joke|funny|laugh|thanks?|thank you|bored|tired|sad|lonely|love you|"
    r"how are you|who are you|what is|what are|what's|why|explain|tell me about|meaning of|"
    r"good (?:morning|night|evening))\b")


class CompanionAgent(SubAgent):
    spec = AgentSpec(
        name="companion",
        role="be the user's friendly companion: chat, jokes, feelings and general "
             "knowledge questions. You never use PC tools: answer with finish.",
        tools=frozenset({"finish"}))
    domain = _CHAT

    def claim(self, session, text: str, ctx: AgentContext) -> AgentReply | None:
        emote = match_emote(text)  # body commands: instant, no model
        if emote is None:
            return None
        session.add_exchange(text, emote["text"])
        return AgentReply(text=emote["text"], animation=emote["animation"],
                          motion=emote["motion"], agent=self.name)

    def score(self, text: str) -> int:
        bonus = 2 if mood_animation(text) else 0  # "I'm tired", "thanks", "joke"
        return super().score(text) + bonus
