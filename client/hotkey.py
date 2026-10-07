"""Global "call Bro" hotkey (Win32 RegisterHotKey on a dedicated thread).

Per-user, no admin rights. The thread owns its own message loop; WM_HOTKEY is
re-emitted as a Qt signal (queued onto the GUI thread automatically).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import sys
import threading

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("arun.client.hotkey")

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
_MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
              "shift": MOD_SHIFT, "win": MOD_WIN}


def parse_hotkey(text: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+B' -> (modifiers, virtual-key). None if invalid."""
    parts = [p.strip().lower() for p in (text or "").split("+") if p.strip()]
    if len(parts) < 2:
        return None
    modifiers = 0
    for part in parts[:-1]:
        if part not in _MODIFIERS:
            return None
        modifiers |= _MODIFIERS[part]
    key = parts[-1]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        vk = 0x70 + int(key[1:]) - 1
    elif key == "space":
        vk = 0x20
    else:
        return None
    return modifiers, vk


class GlobalHotkey(QObject):
    pressed = pyqtSignal()

    def __init__(self, text: str):
        super().__init__()
        self.text = text
        self._thread_id: int | None = None

    def start(self) -> None:
        parsed = parse_hotkey(self.text)
        if sys.platform != "win32" or parsed is None:
            logger.warning("global hotkey disabled (%r)", self.text)
            return
        threading.Thread(target=self._run, args=parsed, daemon=True,
                         name="arun-hotkey").start()

    def _run(self, modifiers: int, vk: int) -> None:
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, modifiers | MOD_NOREPEAT, vk):
            logger.warning("could not register hotkey %s (in use by another app?)",
                           self.text)
            return
        logger.info("global hotkey %s registered", self.text)
        msg = wt.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    self.pressed.emit()
        finally:
            user32.UnregisterHotKey(None, 1)

    def stop(self) -> None:
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
