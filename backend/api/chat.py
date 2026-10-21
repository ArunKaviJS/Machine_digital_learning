"""POST /chat — a conversation with Arun in the chat window.

Every message goes to the MainAgent (backend/agents/main_agent.py), which
assigns it to one sub-agent (companion, writer, window, system, stats,
general). A chat keeps its history: a sub-agent can ask the user a question
mid-task (status "question") and the next message goes back to it; after a
task the user can keep typing more work ("open notepad" -> "write how are
you" types into that Notepad). The context is saved to SQLite after every
message and deleted when the chat is closed (DELETE /chat/{id}).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.agents.base import AgentContext
from backend.agents.main_agent import AI_DOWN, NOT_UNDERSTOOD, MainAgent  # noqa: F401

router = APIRouter()


class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    session_id: str | None = Field(None, max_length=64)


class ChatResponse(BaseModel):
    session_id: str
    text: str
    animation: str
    status: Literal["done", "question", "stuck"]
    steps: list[dict[str, Any]] = []
    motion: str | None = None  # on-screen move for the character (emotes)
    agent: str = ""            # which sub-agent answered


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request) -> ChatResponse:
    state = request.app.state
    engine = getattr(state, "agent", None)
    if engine is None or not engine.enabled:
        raise HTTPException(503, "Chat needs Ollama — AI is turned off or not ready.")
    session = engine.sessions.get_or_create(body.session_id)
    if not session.lock.acquire(blocking=False):
        raise HTTPException(409, "Still working on your last message, bro.")
    try:
        reply = MainAgent(AgentContext.from_state(state)).handle(session, body.text)
        return ChatResponse(session_id=session.id, text=reply.text,
                            animation=reply.animation, status=reply.status,
                            steps=reply.steps, motion=reply.motion, agent=reply.agent)
    finally:
        engine.sessions.save(session)  # context memory lives in SQLite
        session.lock.release()


@router.delete("/chat/{session_id}")
def end_chat(session_id: str, request: Request) -> dict[str, bool]:
    engine = getattr(request.app.state, "agent", None)
    return {"ended": bool(engine and engine.sessions.end(session_id))}
