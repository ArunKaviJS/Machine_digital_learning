"""Interactive popups for server-pushed events (SKILL §18): water reminders,
doomscroll-guard nags/countdowns.

Unlike SpeechBubble (pure display, fine to live under the character window's
non-activating always-on-top style), these need real clicks to register, so
they're independent top-level widgets — parenting an interactive dialog to a
WS_EX_NOACTIVATE window can leave it unable to gain focus (see
character_window.py's "Ask Bro" fix for the same lesson).
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

_PANEL_STYLE = ("background-color: #ffffff; border: 2px solid {border}; "
               "border-radius: 14px;")
_LABEL_STYLE = "color: {color}; font-size: 13px; border: none;"
_BTN_PRIMARY = ("background-color: {color}; color: white; border: none; "
               "border-radius: 8px; padding: 6px 14px; font-weight: bold;")
_BTN_SECONDARY = ("background-color: #eef3fb; color: #1f4a85; border: none; "
                  "border-radius: 8px; padding: 6px 14px;")

_BLUE = "#1f4a85"
_RED = "#c9432f"


def _place(widget: QWidget, anchor: QPoint) -> None:
    """Center above `anchor`, but never off-screen: with enough items (e.g.
    CommandsPanel) a widget placed purely above the anchor can land with a
    negative y and render almost entirely above the visible desktop —
    confirmed via UI Automation (Rect y=-612) to be fully unreachable by a
    real mouse. Flip below the anchor when there's no room above, then clamp
    both axes to the actual screen's available geometry."""
    widget.adjustSize()
    x = anchor.x() - widget.width() // 2
    y = anchor.y() - widget.height() - 16
    screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
    if screen is not None:
        area = screen.availableGeometry()
        if y < area.top():
            y = anchor.y() + 16  # not enough room above; place below instead
        x = max(area.left(), min(x, area.right() - widget.width()))
        y = max(area.top(), min(y, area.bottom() - widget.height()))
    widget.move(x, y)
    widget.show()
    widget.raise_()
    widget.activateWindow()


class WaterReminderPopup(QWidget):
    """One-shot popup for a `water_due` event. YES / Remind me later."""

    yes = pyqtSignal()
    later = pyqtSignal()

    def __init__(self, count: int, target: int) -> None:
        super().__init__(
            None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(_PANEL_STYLE.format(border=_BLUE))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        label = QLabel(f"Time to drink water, bro! ({count}/{target} glasses today)")
        label.setWordWrap(True)
        label.setMaximumWidth(220)
        label.setStyleSheet(_LABEL_STYLE.format(color=_BLUE))
        layout.addWidget(label)

        row = QHBoxLayout()
        yes_btn = QPushButton("YES")
        yes_btn.setStyleSheet(_BTN_PRIMARY.format(color=_BLUE))
        yes_btn.clicked.connect(self._on_yes)
        later_btn = QPushButton("Remind me later")
        later_btn.setStyleSheet(_BTN_SECONDARY)
        later_btn.clicked.connect(self._on_later)
        row.addWidget(yes_btn)
        row.addWidget(later_btn)
        layout.addLayout(row)

    def _on_yes(self) -> None:
        self.yes.emit()
        self.close()

    def _on_later(self) -> None:
        self.later.emit()
        self.close()

    def show_near(self, anchor: QPoint) -> None:
        _place(self, anchor)


class QuestionPopup(QWidget):
    """Yes/no question (e.g. "You haven't used WhatsApp for 30 min — shall I
    close it?"). Nothing happens unless the user clicks yes."""

    yes = pyqtSignal()
    no = pyqtSignal()

    def __init__(self, text: str, yes_label: str, no_label: str) -> None:
        super().__init__(
            None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(_PANEL_STYLE.format(border=_BLUE))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(240)
        label.setStyleSheet(_LABEL_STYLE.format(color=_BLUE))
        layout.addWidget(label)

        row = QHBoxLayout()
        yes_btn = QPushButton(yes_label)
        yes_btn.setStyleSheet(_BTN_PRIMARY.format(color=_BLUE))
        yes_btn.clicked.connect(self._on_yes)
        no_btn = QPushButton(no_label)
        no_btn.setStyleSheet(_BTN_SECONDARY)
        no_btn.clicked.connect(self._on_no)
        row.addWidget(yes_btn)
        row.addWidget(no_btn)
        layout.addLayout(row)

    def _on_yes(self) -> None:
        self.yes.emit()
        self.close()

    def _on_no(self) -> None:
        self.no.emit()
        self.close()

    def show_near(self, anchor: QPoint) -> None:
        _place(self, anchor)


class GuardBanner(QWidget):
    """Persistent nag/countdown banner for the doomscroll guard — created
    once by CharacterWindow and updated in place rather than recreated."""

    cancel = pyqtSignal()
    snooze = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(
            None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_PANEL_STYLE.format(border=_RED))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(220)
        self._label.setStyleSheet(_LABEL_STYLE.format(color=_RED))
        layout.addWidget(self._label)

        row = QHBoxLayout()
        self._cancel_btn = QPushButton("I'm done here")
        self._cancel_btn.setStyleSheet(_BTN_PRIMARY.format(color=_RED))
        self._cancel_btn.clicked.connect(self.cancel)
        self._snooze_btn = QPushButton("5 more minutes")
        self._snooze_btn.setStyleSheet(_BTN_SECONDARY)
        self._snooze_btn.clicked.connect(self.snooze)
        row.addWidget(self._cancel_btn)
        row.addWidget(self._snooze_btn)
        layout.addLayout(row)
        self.hide()

    def show_nag(self, site: str, anchor: QPoint) -> None:
        self._label.setText(f"Still on {site}, bro — thinking about a break?")
        _place(self, anchor)

    def show_countdown(self, site: str, seconds_left: int, anchor: QPoint) -> None:
        self._label.setText(f"Closing {site} in {seconds_left}s, bro!")
        _place(self, anchor)


class CommandsPanel(QWidget):
    """Right-click replacement for QMenu: a plain button list, not Qt's
    native popup-menu machinery. On this character window (always-on-top,
    WS_EX_NOACTIVATE), QMenu.exec() was confirmed — via real OS-level
    WM_RBUTTONDOWN/UP messages posted straight at the window, not just mouse
    clicks — to never deliver item activations at all, so every entry was
    unreachable regardless of what it did. Plain QPushButtons in an
    independent top-level widget use ordinary button click delivery instead,
    the same mechanism already confirmed working for this window's own
    left-click handling."""

    def __init__(self, items: list[tuple[str, Callable[[], None]]]) -> None:
        super().__init__(
            None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(_PANEL_STYLE.format(border=_BLUE))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        for label, callback in items:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "background-color: #eef3fb; color: #1f4a85; border: none; "
                "border-radius: 8px; padding: 6px 12px; text-align: left;")
            btn.clicked.connect(lambda checked=False, cb=callback: self._activate(cb))
            layout.addWidget(btn)

    def _activate(self, callback: Callable[[], None]) -> None:
        self.close()
        callback()

    def show_near(self, anchor: QPoint) -> None:
        _place(self, anchor)
