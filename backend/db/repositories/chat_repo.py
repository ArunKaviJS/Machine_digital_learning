"""chat_sessions / chat_messages: a chat's context memory, kept only while
the chat is open (deleted when the user closes it or it goes idle)."""

from __future__ import annotations

import json
from typing import Any

from backend.db.connection import Database


class ChatRepo:
    def __init__(self, db: Database):
        self.db = db

    def save(self, session_id: str, *, now: float, request: str, awaiting_answer: bool,
             user_texts: list[str], active_window: dict[str, Any] | None,
             messages: list[dict[str, str]]) -> None:
        """Replace the stored state of one chat (history is capped, so the
        full rewrite stays small)."""
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO chat_sessions(id, created_at, updated_at, request,"
                " awaiting_answer, user_texts, active_window) VALUES(?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at,"
                " request = excluded.request, awaiting_answer = excluded.awaiting_answer,"
                " user_texts = excluded.user_texts, active_window = excluded.active_window",
                (session_id, now, now, request, 1 if awaiting_answer else 0,
                 json.dumps(user_texts), json.dumps(active_window) if active_window else None))
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            conn.executemany(
                "INSERT INTO chat_messages(session_id, seq, role, content) VALUES(?,?,?,?)",
                [(session_id, i, m["role"], m["content"]) for i, m in enumerate(messages)])

    def load(self, session_id: str) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM chat_sessions WHERE id = ?", (session_id,))
        if row is None:
            return None
        msgs = self.db.query("SELECT role, content FROM chat_messages WHERE session_id = ?"
                             " ORDER BY seq", (session_id,))
        return {"id": row["id"], "updated_at": row["updated_at"], "request": row["request"],
                "awaiting_answer": bool(row["awaiting_answer"]),
                "user_texts": json.loads(row["user_texts"]),
                "active_window": json.loads(row["active_window"]) if row["active_window"] else None,
                "messages": [{"role": m["role"], "content": m["content"]} for m in msgs]}

    def delete(self, session_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))

    def purge_older_than(self, cutoff: float) -> int:
        """Drop chats idle since before `cutoff` (epoch seconds)."""
        ids = [r["id"] for r in self.db.query(
            "SELECT id FROM chat_sessions WHERE updated_at < ?", (cutoff,))]
        for sid in ids:
            self.delete(sid)
        return len(ids)

    def count(self) -> int:
        return int(self.db.query_one("SELECT COUNT(*) AS n FROM chat_sessions")["n"])
