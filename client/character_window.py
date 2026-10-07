"""Transparent, always-on-top, non-activating character window (SKILL §20).

Click vs drag distinction, right-click commands panel, and reactions to
server-pushed events (water reminders, doomscroll guard, unused apps) over the
/ws/events WebSocket. presence="on_demand" (default): hidden in the tray until
called (tray click / global hotkey) or until an event needs attention, then
stands still and auto-hides; presence="always": always visible, roaming.

Right-click opens a plain-button CommandsPanel, not a QMenu: confirmed via
direct WM_RBUTTONDOWN/UP messages posted at the window that Qt's native
context-menu popup never activates on this always-on-top, WS_EX_NOACTIVATE
window, so every item was unreachable regardless of what it did.
"""

from __future__ import annotations

import ctypes
import logging
import random
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QByteArray, QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import QMouseEvent, QPainter, QPaintEvent, QTransform
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication, QInputDialog, QLabel, QWidget

from client.animation import AnimationPlayer
from client.placeholder_svg import ANIMATION_CYCLE, character_svg
from client.popups import CommandsPanel, GuardBanner, QuestionPopup, WaterReminderPopup
from client.walk_area import random_target, roam_bounds, step_toward
from client.ws_client import EventClient

logger = logging.getLogger("arun.client")

CHAR_WIDTH = 160
CHAR_HEIGHT = 220
WALK_SPEED = 4.0          # px per tick
CLICK_DRAG_THRESHOLD = 4   # px: more than this between press/release = a drag
IDLE_PAUSE_TICKS_RANGE = (24, 96)  # ~1-4s at 24fps between wanders
BUBBLE_VISIBLE_MS = 2500

# One-click commands in the right-click CommandsPanel (SKILL §7): these go
# straight to the backend with no secondary dialog window to open/focus — a
# dialog needs real OS window activation, which this always-on-top,
# non-activating character window may not reliably get from Windows' anti-
# focus-stealing heuristics. "Ask Bro..." (free text) stays available too,
# for anything not covered here.
QUICK_COMMANDS: list[tuple[str, str]] = [
    ("Open YouTube", "open youtube"),
    ("Open Instagram", "open instagram"),
    ("Close the YouTube tab", "close the youtube tab"),
    ("Close the Instagram tab", "close that instagram tab"),
    ("How much YouTube today?", "how much youtube did i use today"),
    ("What's my screen time today?", "how much screen time today"),
    ("I drank a glass of water", "i drank a glass of water"),
    ("How much water today?", "how much water did i drink today"),
    ("Tidy my downloads folder", "tidy my downloads folder"),
    ("Undo that", "undo that"),
]


class SpeechBubble(QWidget):
    """Tiny always-on-top popup shown above the character on click (UI-level
    feedback instead of a terminal-only log line)."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(220)
        self._label.setStyleSheet(
            "background-color: #ffffff; color: #2a2a35;"
            "border: 2px solid #2a2a35; border-radius: 12px;"
            "padding: 8px 12px; font-size: 13px;"
        )

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_message(self, text: str, anchor_global: QPoint) -> None:
        self._label.setText(text)
        self._label.adjustSize()
        self.resize(self._label.size())
        self.move(anchor_global.x() - self.width() // 2, anchor_global.y() - self.height() - 12)
        self.show()
        self._hide_timer.start(BUBBLE_VISIBLE_MS)


def _alive_visible(widget: QWidget | None) -> bool:
    """isVisible() that tolerates WA_DeleteOnClose popups already destroyed."""
    if widget is None:
        return False
    try:
        return widget.isVisible()
    except RuntimeError:  # wrapped C/C++ object has been deleted
        return False


GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


def _apply_noactivate_style(hwnd: int) -> None:
    """Belt-and-braces on top of Qt's WindowDoesNotAcceptFocus (SKILL §22)."""
    if sys.platform != "win32" or not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        style = get_style(hwnd, GWL_EXSTYLE)
        set_style(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except Exception:
        logger.exception("could not apply WS_EX_NOACTIVATE|WS_EX_TOOLWINDOW")


class CharacterWindow(QWidget):
    def __init__(self, config: dict[str, Any], api_client: Any | None = None):
        super().__init__()
        self.config = config
        self.api = api_client
        self.facing_right = bool(config.get("walkFacesRight", True))
        # "on_demand": hidden in the tray until called (tray / hotkey) or until
        # Bro has something to say, then stands still and auto-hides.
        # "always": the original always-visible, desktop-roaming mode.
        self.presence = config.get("presence", "on_demand")
        self.walking_enabled = (bool(config.get("walking", True))
                                and self.presence == "always")

        assets_dir = Path(__file__).resolve().parent.parent / "assets" / "stickers" \
            / config.get("character", "arun")
        self.player = AnimationPlayer(assets_dir, fps=int(config.get("fps", 24)))

        self._press_pos: QPoint | None = None
        self._dragging = False
        self._svg_cache: dict[str, QSvgRenderer] = {}
        self._wander_target: tuple[float, float] | None = None
        self._idle_ticks_left = 0
        self._anim_frame = 0
        self._bubble = SpeechBubble()
        self._guard_banner = GuardBanner()
        self._guard_banner.cancel.connect(self._action_guard_cancel)
        self._guard_banner.snooze.connect(self._action_guard_snooze)
        self._water_popup: WaterReminderPopup | None = None
        self._commands_panel: CommandsPanel | None = None
        self._question_popup: QuestionPopup | None = None
        self._idle_question_key: str | None = None
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._maybe_auto_hide)
        self._nag_hide_timer = QTimer(self)
        self._nag_hide_timer.setSingleShot(True)
        self._nag_hide_timer.timeout.connect(self._guard_banner.hide)
        # Reactions (click, Ask Bro, popups) set a non-idle/walk pose; without
        # this, _on_tick's wander gate (pose in idle/walk) never re-opens and
        # the character freezes in place forever after the first reaction.
        self._reaction_timer = QTimer(self)
        self._reaction_timer.setSingleShot(True)
        self._reaction_timer.timeout.connect(self._end_reaction)

        self._configure_window()
        self._position_initial()

        self._timer = QTimer(self)
        interval = max(1, 1000 // max(1, int(config.get("fps", 24))))
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(interval)

        self._events = EventClient(config) if self.api is not None else None
        if self._events is not None:
            self._events.message.connect(self._on_server_event)
            self._events.start()

    # -- setup -------------------------------------------------------------
    def _configure_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # Qt's default ContextMenuPolicy routes right-button presses to
        # contextMenuEvent() before mousePressEvent() ever sees them — with
        # no override, that silently swallows every right-click. NoContextMenu
        # makes right-clicks ordinary mouse events, same path as left-clicks
        # (confirmed working via real hardware AND synthetic PostMessage).
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.resize(CHAR_WIDTH, CHAR_HEIGHT)

    def _position_initial(self) -> None:
        if self.presence != "always":
            self._move_home()
            return
        min_x, min_y, max_x, max_y = self._roam_bounds()
        self._x, self._y = random_target(min_x, min_y, max_x, max_y)
        self.move(int(self._x), int(self._y))

    def _move_home(self) -> None:
        """Bottom-right corner, just above the taskbar near the tray icon."""
        screen = self.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self._x = float(area.right() - self.width() - 24)
        self._y = float(area.bottom() - self.height())
        self.move(int(self._x), int(self._y))

    # -- presence (on_demand: tray / hotkey / events) -----------------------
    def toggle(self) -> None:
        """Tray click / hotkey: call Bro, or send him back to the tray."""
        if self.isVisible():
            self.dismiss()
        else:
            self.appear(greet=True)

    def appear(self, greet: bool = False) -> None:
        if not self.isVisible():
            if self.presence != "always":
                self._move_home()
            self.show()
        self.raise_()
        if greet:
            self._react("greeting")
            name = self.config.get("userName", "bro")
            self._bubble.show_message(
                f"Hey {name}! Right-click me for commands.", self._anchor())
        self._touch()

    def dismiss(self) -> None:
        if self.presence == "always":
            return
        self._auto_hide_timer.stop()
        self._bubble.hide()
        self.hide()

    def _touch(self) -> None:
        """Any interaction restarts the auto-hide countdown."""
        if self.presence != "always":
            self._auto_hide_timer.start(int(self.config.get("autoHideSeconds", 45)) * 1000)

    def _busy(self) -> bool:
        """Never vanish mid-conversation: popups open or a reply pending."""
        popups = (self._water_popup, self._question_popup, self._commands_panel,
                  self._guard_banner)
        return self.player.pose == "thinking" or any(_alive_visible(p) for p in popups)

    def _maybe_auto_hide(self) -> None:
        if self._busy():
            self._touch()
        else:
            self.dismiss()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        _apply_noactivate_style(int(self.winId()))

    # -- paint ---------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pixmap = self.player.current_pixmap()
        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaledToHeight(
                self.height(), Qt.TransformationMode.SmoothTransformation)
            if not self.facing_right:
                scaled = scaled.transformed(QTransform().scale(-1, 1))
            painter.drawPixmap(0, 0, scaled)
        else:
            self._paint_placeholder(painter)
        painter.end()

    def _paint_placeholder(self, painter: QPainter) -> None:
        """No artwork yet (need-to-do.md §E): an animated SVG approximation
        of a cat, keyed by pose + animation frame (CONTEXT.md D17)."""
        renderer = self._svg_renderer_for(self.player.pose, self._anim_frame // 3)
        view_box = renderer.viewBoxF()
        box_w = self.width() if not view_box.height() \
            else min(self.width(), self.height() * view_box.width() / view_box.height())
        target = QRectF((self.width() - box_w) / 2, 0, box_w, self.height())

        if not self.facing_right:
            painter.save()
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        renderer.render(painter, target)
        if not self.facing_right:
            painter.restore()

    def _svg_renderer_for(self, pose: str, frame: int) -> QSvgRenderer:
        key = f"{pose}:{frame % ANIMATION_CYCLE}"
        if key not in self._svg_cache:
            svg = character_svg(pose, frame % ANIMATION_CYCLE)
            self._svg_cache[key] = QSvgRenderer(QByteArray(svg.encode()))
        return self._svg_cache[key]

    # -- reactions ---------------------------------------------------------
    def _react(self, pose: str, duration_ms: int = 2500) -> None:
        """Show a transient reaction pose, then resume idle/walk wandering."""
        self.player.set_pose(pose)
        if pose in ("idle", "walk"):
            self._reaction_timer.stop()
            return
        self._reaction_timer.start(duration_ms)

    def _end_reaction(self) -> None:
        self.player.set_pose("idle")

    # -- tick / wandering --------------------------------------------------
    def _roam_bounds(self) -> tuple[int, int, int, int]:
        screen = self.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        return roam_bounds(area.left(), area.top(), area.right(), area.bottom(),
                            self.width(), self.height())

    def _on_tick(self) -> None:
        self.player.advance()
        self._anim_frame += 1
        if self.walking_enabled and self.player.pose in ("idle", "walk"):
            if self._idle_ticks_left > 0:
                self._idle_ticks_left -= 1
                self.player.set_pose("idle")
            else:
                self.player.set_pose("walk")
                self._wander_step()
        self.update()

    def _wander_step(self) -> None:
        if self._wander_target is None:
            min_x, min_y, max_x, max_y = self._roam_bounds()
            self._wander_target = random_target(min_x, min_y, max_x, max_y)
        target_x, target_y = self._wander_target
        self._x, self._y, self.facing_right, arrived = step_toward(
            self._x, self._y, target_x, target_y, WALK_SPEED)
        self.move(int(self._x), int(self._y))
        if arrived:
            self._wander_target = None
            self._idle_ticks_left = random.randint(*IDLE_PAUSE_TICKS_RANGE)

    # -- mouse: click vs drag --------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._drag_origin = self.pos()
            self._dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            # Not a QMenu: confirmed via real OS-level WM_RBUTTONDOWN/UP
            # messages posted straight at this window that Qt's context-menu
            # popup never activates here (always-on-top, WS_EX_NOACTIVATE).
            # Plain button clicks (this window's own left-click handling,
            # and buttons inside CommandsPanel) are the mechanism that's
            # actually confirmed to work.
            self._show_commands_panel()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._press_pos is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = event.globalPosition().toPoint() - self._press_pos
        if abs(delta.x()) > CLICK_DRAG_THRESHOLD or abs(delta.y()) > CLICK_DRAG_THRESHOLD:
            self._dragging = True
            self.move(self._drag_origin + delta)
            self._x, self._y = float(self.pos().x()), float(self.pos().y())
            self._wander_target = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._dragging:
            self._on_click()
        self._press_pos = None
        self._dragging = False

    def _on_click(self) -> None:
        """Hey bro! greeting (no AI, SKILL §7). Menu panels arrive in M12."""
        self._react("greeting")
        self._touch()
        name = self.config.get("userName", "bro")
        logger.info("Hey %s! \U0001F44B", name)
        self._bubble.show_message(f"Hey {name}! \U0001F44B", self._anchor())

    # -- commands panel (thin; call backend, ignore failures) ------------
    def _show_commands_panel(self) -> None:
        self._touch()
        items: list[tuple[str, Any]] = [
            (label, (lambda t=text: self._ask_text(t))) for label, text in QUICK_COMMANDS
        ]
        items += [
            ("Ask Bro (type your own)...", self._action_ask),
            ("Remind me to drink now", self._action_drink_reminder),
            ("Pause Arun (DND)", self._action_toggle_pause),
            ("Clear chat", self._action_clear_chat),
            ("Start at login", self._action_toggle_autostart),
        ]
        if self.presence != "always":
            items.append(("Hide Bro (back to tray)", self.dismiss))
        items.append(("Quit", self._action_quit))
        self._commands_panel = CommandsPanel(items)
        self._commands_panel.show_near(self._anchor())

    def _action_ask(self) -> None:
        # Unparented on purpose: `self` is a non-activating, always-on-top
        # tool window (WS_EX_NOACTIVATE/TOOLWINDOW) — a dialog parented to it
        # can open without ever gaining focus or raising itself on Windows.
        # The stays-on-top hint is passed to the constructor, not applied via
        # setWindowFlags() afterward — changing flags on an already-created
        # widget forces Qt to recreate and hide it, which can leave it
        # unfocusable depending on how reliably exec() re-shows it.
        dialog = QInputDialog(None, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        dialog.setWindowTitle("Ask Bro")
        dialog.setLabelText("What do you want, bro?")
        ok = dialog.exec() == QInputDialog.DialogCode.Accepted
        text = dialog.textValue().strip()
        if not ok or not text:
            return
        self._ask_text(text)

    def _ask_text(self, text: str) -> None:
        self._react("thinking", duration_ms=15000)  # fallback if the reply never arrives
        self._touch()
        if self.api is None:
            return
        anchor = self._anchor()
        self.api.call("post", "/ask", json={"text": text},
                      on_done=lambda result: self._on_ask_response(result, anchor),
                      on_error=lambda err: self._on_ask_error(anchor))

    def _on_ask_response(self, result: dict, anchor: QPoint) -> None:
        self._react(result.get("animation") or "idle")
        self._bubble.show_message(result.get("text") or "...", anchor)
        self._touch()

    def _on_ask_error(self, anchor: QPoint) -> None:
        self._react("confused")
        self._bubble.show_message("Couldn't reach the backend, bro.", anchor)
        self._touch()

    def _action_drink_reminder(self) -> None:
        self._call_api("post", "/water/drink")

    def _action_toggle_pause(self) -> None:
        self._call_api("post", "/pause")

    def _action_clear_chat(self) -> None:
        self._bubble.hide()  # no chat box yet (M12)

    def _action_toggle_autostart(self) -> None:
        self._call_api("post", "/system/autostart", json={"enabled": True})

    def _action_quit(self) -> None:
        self._bubble.close()
        self._guard_banner.close()
        for popup in (self._water_popup, self._commands_panel, self._question_popup):
            if _alive_visible(popup):
                popup.close()
        if self._events is not None:
            self._events.stop()
        QApplication.quit()

    quit_app = _action_quit

    def _anchor(self) -> QPoint:
        return self.mapToGlobal(QPoint(self.width() // 2, 0))

    # -- server-pushed events (water, doomscroll guard, unused apps) ------
    # events that need the user's attention bring Bro out of the tray
    _ATTENTION_EVENTS = {"water_due", "nag", "countdown_start", "countdown_tick",
                         "tab_closed", "idle_app"}

    def _on_server_event(self, payload: dict) -> None:
        handler = {
            "water_due": self._on_water_due,
            "nag": self._on_guard_nag,
            "countdown_start": self._on_guard_countdown,
            "countdown_tick": self._on_guard_countdown,
            "tab_closed": self._on_guard_tab_closed,
            "cancelled": self._on_guard_cleared,
            "idle_app": self._on_idle_app,
            "idle_app_cleared": self._on_idle_app_cleared,
        }.get(payload.get("type"))
        if handler is None:
            return
        if payload.get("type") in self._ATTENTION_EVENTS:
            self.appear()
        handler(payload)

    def _on_idle_app(self, payload: dict) -> None:
        key, name = payload.get("key"), payload.get("name") or "that app"
        minutes = payload.get("minutes", 30)
        if _alive_visible(self._question_popup):
            self._question_popup.close()
        self._react("thinking", duration_ms=60000)
        popup = QuestionPopup(
            f"You haven't used {name} for {minutes} min, bro. Shall I close it?",
            "Yes, close it", "Keep it")
        popup.yes.connect(lambda: self._answer_idle_app(key, True))
        popup.no.connect(lambda: self._answer_idle_app(key, False))
        self._question_popup = popup
        self._idle_question_key = key
        popup.show_near(self._anchor())

    def _answer_idle_app(self, key: str, close: bool) -> None:
        self._idle_question_key = None
        self._touch()
        if self.api is None:
            self._end_reaction()
            return
        anchor = self._anchor()
        self.api.call("post", "/apps/idle/answer", json={"key": key, "close": close},
                      on_done=lambda result: self._on_ask_response(result, anchor),
                      on_error=lambda err: self._on_ask_error(anchor))

    def _on_idle_app_cleared(self, payload: dict) -> None:
        if payload.get("key") != self._idle_question_key:
            return
        self._idle_question_key = None
        if _alive_visible(self._question_popup):
            self._question_popup.close()
        self._end_reaction()

    def _on_water_due(self, payload: dict) -> None:
        self._react("water", duration_ms=45000)  # generous: popup may sit open a while
        self._water_popup = WaterReminderPopup(payload.get("count", 0),
                                               payload.get("target", 8))
        self._water_popup.yes.connect(self._action_water_yes)
        self._water_popup.later.connect(self._action_water_later)
        self._water_popup.show_near(self._anchor())

    def _action_water_yes(self) -> None:
        self._react("happy")
        self._touch()
        self._bubble.show_message("Nice! \U0001F44D", self._anchor())
        self._call_api("post", "/water/drink")

    def _action_water_later(self) -> None:
        self._end_reaction()
        self._touch()
        self._call_api("post", "/water/snooze")

    def _on_guard_nag(self, payload: dict) -> None:
        self._react("warn", duration_ms=20000)
        site = payload.get("site") or "that site"
        self._guard_banner.show_nag(site, self._anchor())
        self._nag_hide_timer.start(20_000)

    def _on_guard_countdown(self, payload: dict) -> None:
        self._react("angry", duration_ms=8000)  # bridges the ~2s gap between ticks
        self._nag_hide_timer.stop()
        site = payload.get("site") or "that site"
        self._guard_banner.show_countdown(site, payload.get("seconds_left", 0),
                                          self._anchor())

    def _on_guard_tab_closed(self, payload: dict) -> None:
        self._nag_hide_timer.stop()
        self._guard_banner.hide()
        self._react("angry", duration_ms=4000)
        site = payload.get("site") or "it"
        self._bubble.show_message(f"Closed {site} for you, bro! \U0001F4A5", self._anchor())

    def _on_guard_cleared(self, payload: dict) -> None:
        self._nag_hide_timer.stop()
        self._guard_banner.hide()
        self._end_reaction()

    def _action_guard_cancel(self) -> None:
        self._nag_hide_timer.stop()
        self._guard_banner.hide()
        self._end_reaction()
        self._touch()
        self._call_api("post", "/guard/cancel")

    def _action_guard_snooze(self) -> None:
        self._nag_hide_timer.stop()
        self._guard_banner.hide()
        self._end_reaction()
        self._touch()
        self._call_api("post", "/guard/snooze")

    def _call_api(self, method: str, path: str, **kwargs) -> None:
        if self.api is None:
            return
        try:
            self.api.call(method, path, **kwargs)
        except Exception:
            logger.exception("context menu action %s %s failed", method, path)
