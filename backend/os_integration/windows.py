"""Windows OS adapter: ctypes + psutil (SKILL §22). No pywin32 needed."""

from __future__ import annotations

import ctypes
import ctypes.wintypes  # noqa: F401  (defines wintypes for GetWindowThreadProcessId)
import logging
import sys
from typing import Any

from backend.os_integration.base import OSAdapter
from backend.os_integration.helpers import is_dnd_app

logger = logging.getLogger("arun.os")

# QUERY_USER_NOTIFICATION_STATE values (shell32.SHQueryUserNotificationState)
QUNS_ACCEPTS_NOTIFICATIONS = 0
_BUSY_STATES = {1, 2, 3, 4, 5, 6}  # unavailable/busy/d3d-fullscreen/presentation/quiet/app

VK_CONTROL = 0x11
VK_W = 0x57
KEYEVENTF_KEYUP = 0x0002


class WindowsOSAdapter(OSAdapter):
    def __init__(self, dnd_apps: list[str] | None = None):
        self.dnd_apps = dnd_apps or []
        self._user32 = ctypes.windll.user32
        self._shell32 = ctypes.windll.shell32
        self._kernel32 = ctypes.windll.kernel32

    # ---- windows ----

    def get_foreground_window(self) -> dict[str, Any] | None:
        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            return None  # lock screen / no window
        buf = ctypes.create_unicode_buffer(512)
        self._user32.GetWindowTextW(hwnd, buf, 512)
        pid = ctypes.wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = None
        if pid.value:
            try:
                import psutil

                process_name = psutil.Process(pid.value).name()
            except Exception as exc:  # process exited, access denied
                logger.debug("psutil failed for pid %s: %s", pid.value, exc)
        return {
            "hwnd": int(hwnd),
            "pid": int(pid.value),
            "process_name": process_name,
            "title": buf.value,
        }

    # ---- idle ----

    def get_idle_seconds(self) -> float:
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not self._user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0
        tick = self._kernel32.GetTickCount()
        elapsed_ms = (tick - lii.dwTime) & 0xFFFFFFFF
        return max(0.0, elapsed_ms / 1000.0)

    # ---- DND ----

    def is_dnd_active(self) -> bool:
        state = ctypes.c_ulong()
        if self._shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0:
            if state.value in _BUSY_STATES:
                return True
        # meeting apps in the foreground (config list)
        fg = self.get_foreground_window()
        if fg and is_dnd_app(fg.get("process_name"), self.dnd_apps):
            return True
        return False

    # ---- close tab (Ctrl+W) ----

    def send_close_tab(self) -> bool:
        try:
            self._user32.keybd_event(VK_CONTROL, 0, 0, 0)
            self._user32.keybd_event(VK_W, 0, 0, 0)
            self._user32.keybd_event(VK_W, 0, KEYEVENTF_KEYUP, 0)
            self._user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as exc:
            logger.error("send_close_tab failed: %s", exc)
            return False

    # ---- autostart ----

    def set_autostart(self, enabled: bool) -> None:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                if getattr(sys, "frozen", False):
                    command = f'"{sys.executable}"'
                else:
                    from backend.config import PROJECT_ROOT

                    command = f'"{sys.executable}" "{PROJECT_ROOT / "run.py"}"'
                winreg.SetValueEx(key, "Arun", 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, "Arun")
                except FileNotFoundError:
                    pass
