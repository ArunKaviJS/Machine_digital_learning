"""Chat window (right-click menu / tray → "Chat with Bro").

A normal, focusable top-level window (not a child of the non-activating
character window — see popups.py for why). It keeps one backend chat
session: Arun may ask a question mid-task (the next message answers it),
and after a job is done the user can keep typing more work. Closing the
window only hides it; "New chat" starts a fresh session.
"""

from __future__ import annotations

import html
from typing import Any

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

CHAT_TIMEOUT_S = 120  # an agent turn may run several think/act steps

_BLUE = "#1f4a85"
_USER_STYLE = ("background-color: #1f4a85; color: white; border-radius: 12px; "
               "padding: 8px 10px; font-size: 13px;")
_ARUN_STYLE = ("background-color: #eef3fb; color: #1b2b44; border-radius: 12px; "
               "padding: 8px 10px; font-size: 13px;")
_QUESTION_STYLE = ("background-color: #fff6e0; color: #5a3d00; border: 1px solid #e0a800; "
                   "border-radius: 12px; padding: 8px 10px; font-size: 13px;")
_NOTE_STYLE = "color: #6b7a90; font-size: 11px; padding: 0 4px;"

PLACEHOLDER_NEW = "Ask me anything or give me a job, bro…"
GREETING = ("Hey bro! Tell me what to do — I'll keep at it until it's done, and "
            "ask if I'm not sure. I remember this chat until you close it.")
PLACEHOLDER_ANSWER = "Type your answer…"
PLACEHOLDER_MORE = "Anything else? Add more work or ask a question…"


def steps_summary(steps: list[dict[str, Any]]) -> str:
    """'✓ Opened Notepad. ✗ Couldn't …' lines for the small grey step log."""
    lines = []
    for step in steps:
        mark = "✓" if step.get("ok") else "✗"
        lines.append(f"{mark} {step.get('observation') or step.get('action')}")
    return "\n".join(lines)


class ChatWindow(QWidget):
    animation = pyqtSignal(str)  # character reacts to replies
    motion = pyqtSignal(str)     # "come here", "go left": character moves

    def __init__(self, api: Any) -> None:
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.api = api
        self.session_id: str | None = None
        self.busy = False
        self._discard_reply = False
        self.setWindowTitle("Chat with Bro")
        self.resize(380, 520)
        self.setStyleSheet("background-color: #ffffff;")

        header = QHBoxLayout()
        title = QLabel("💧 Chat with Bro")
        title.setStyleSheet(f"color: {_BLUE}; font-size: 15px; font-weight: bold;")
        self._new_btn = QPushButton("New chat")
        self._new_btn.setStyleSheet(
            "background-color: #eef3fb; color: #1f4a85; border: none; "
            "border-radius: 8px; padding: 4px 10px;")
        self._new_btn.clicked.connect(self.new_chat)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._new_btn)

        self._list = QVBoxLayout()
        self._list.setSpacing(6)
        self._list.addStretch()
        inner = QWidget()
        inner.setLayout(self._list)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(inner)
        self._scroll.setStyleSheet("border: none;")

        self._status = QLabel("")
        self._status.setStyleSheet(_NOTE_STYLE)

        self._input = QLineEdit()
        self._input.setPlaceholderText(PLACEHOLDER_NEW)
        self._input.setStyleSheet("border: 1px solid #c8d4e6; border-radius: 8px; "
                                  "padding: 7px; font-size: 13px; color: #1b2b44;")
        self._input.returnPressed.connect(self.send)
        self._send_btn = QPushButton("Send")
        self._send_btn.setStyleSheet(
            f"background-color: {_BLUE}; color: white; border: none; "
            "border-radius: 8px; padding: 7px 14px; font-weight: bold;")
        self._send_btn.clicked.connect(self.send)
        row = QHBoxLayout()
        row.addWidget(self._input)
        row.addWidget(self._send_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addLayout(header)
        layout.addWidget(self._scroll, 1)
        layout.addWidget(self._status)
        layout.addLayout(row)

        self._add_bubble("arun", GREETING)

    # ---- public ----
    def open_near(self, anchor: QPoint | None = None) -> None:
        if not self.isVisible() and anchor is not None:
            screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
            x, y = anchor.x() - self.width() // 2, anchor.y() - self.height() - 20
            if screen is not None:
                area = screen.availableGeometry()
                x = max(area.left(), min(x, area.right() - self.width()))
                y = max(area.top(), min(y, area.bottom() - self.height()))
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def send(self) -> None:
        text = self._input.text().strip()
        if not text or self.busy:
            return
        self._input.clear()
        self._add_bubble("user", text)
        self._set_busy(True)
        self.animation.emit("thinking")
        if self.api is None:
            self._on_error("no backend")
            return
        self.api.call("post", "/chat", json={"text": text, "session_id": self.session_id},
                      timeout=CHAT_TIMEOUT_S, on_done=self._on_reply, on_error=self._on_error)

    def new_chat(self) -> None:
        if self.busy:
            return
        self._end_chat()
        self._add_bubble("arun", "Fresh start, bro. What's next?")

    def _end_chat(self) -> None:
        """Forget this conversation: the backend deletes its context memory
        (SQLite rows) and the window starts empty next time."""
        if self.session_id and self.api is not None:
            self.api.call("delete", f"/chat/{self.session_id}")
        self.session_id = None
        while self._list.count() > 1:  # keep the trailing stretch
            item = self._list.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._input.setPlaceholderText(PLACEHOLDER_NEW)

    # ---- replies ----
    def _on_reply(self, result: dict) -> None:
        self._set_busy(False)
        if self._discard_reply:  # the chat was closed while Bro was working
            self._discard_reply = False
            if result.get("session_id") and self.api is not None:
                self.api.call("delete", f"/chat/{result['session_id']}")
            return
        self.session_id = result.get("session_id") or self.session_id
        status = result.get("status", "done")
        text = result.get("text") or "…"
        steps = result.get("steps") or []
        if steps:
            self._add_note(steps_summary(steps))
        if status == "question":
            self._add_bubble("question", text)
            self._input.setPlaceholderText(PLACEHOLDER_ANSWER)
        else:
            self._add_bubble("arun", text)
            self._input.setPlaceholderText(PLACEHOLDER_MORE)
            if steps:  # a job just ran: invite follow-up work
                self._add_note("Anything else, bro? Add more work or ask me something.")
        self.animation.emit(result.get("animation") or "idle")
        if result.get("motion"):
            self.motion.emit(result["motion"])

    def _on_error(self, err: str) -> None:
        self._set_busy(False)
        if self._discard_reply:
            self._discard_reply = False
            return
        if "409" in err:
            msg = "Still working on your last message, bro."
        elif "503" in err:
            msg = "My brain (Ollama) isn't running, bro. Start Ollama and try again."
        else:
            msg = "Couldn't reach the backend, bro."
        self._add_bubble("arun", msg)
        self.animation.emit("confused")

    # ---- widgets ----
    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self._send_btn.setEnabled(not busy)
        self._new_btn.setEnabled(not busy)
        self._status.setText("Bro is working on it…" if busy else "")
        if not busy:
            self._input.setFocus()

    def _add_bubble(self, who: str, text: str) -> None:
        label = QLabel(html.escape(text).replace("\n", "<br>"))
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setMaximumWidth(280)
        label.setStyleSheet({"user": _USER_STYLE, "question": _QUESTION_STYLE}
                            .get(who, _ARUN_STYLE))
        row = QHBoxLayout()
        if who == "user":
            row.addStretch()
            row.addWidget(label)
        else:
            row.addWidget(label)
            row.addStretch()
        holder = QWidget()
        holder.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self._list.insertWidget(self._list.count() - 1, holder)
        self._scroll_to_end()

    def _add_note(self, text: str) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(_NOTE_STYLE)
        self._list.insertWidget(self._list.count() - 1, label)
        self._scroll_to_end()

    def _scroll_to_end(self) -> None:
        QTimer.singleShot(0, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Closing the chat ends it: its context memory is deleted (the next
        open starts a fresh conversation). The window itself is reused."""
        event.ignore()
        self._discard_reply = self.busy  # a reply still on its way is dropped
        self._end_chat()
        if self.api is not None:
            self.api.call("post", "/ai/unload")  # give the model's RAM back now
        self._add_bubble("arun", GREETING)
        self.hide()
