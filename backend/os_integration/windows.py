"""Windows OS adapter: ctypes + psutil (SKILL §22). No pywin32 needed."""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes  # noqa: F401  (defines wintypes for GetWindowThreadProcessId)
import logging
import os
import subprocess
import sys
from typing import Any

from backend.os_integration.base import OSAdapter
from backend.os_integration.helpers import is_dnd_app, parse_start_apps_json

logger = logging.getLogger("arun.os")

# QUERY_USER_NOTIFICATION_STATE values (shell32.SHQueryUserNotificationState).
# Per the real Win32 enum (shellapi.h): 1=NOT_PRESENT, 2=BUSY,
# 3=RUNNING_D3D_FULL_SCREEN, 4=PRESENTATION_MODE, 5=ACCEPTS_NOTIFICATIONS
# (the NORMAL state — "notifications can be freely sent"), 6=QUIET_TIME,
# 7=APP. QUNS_ACCEPTS_NOTIFICATIONS is 5, not 0 — a previous off-by-one here
# meant the normal, non-DND state (5) was misclassified as busy, silently
# suppressing every water reminder and doomscroll-guard nag.
QUNS_ACCEPTS_NOTIFICATIONS = 5
_BUSY_STATES = {1, 2, 3, 4, 6, 7}  # not-present/busy/d3d-fullscreen/presentation/quiet-time/app

VK_CONTROL = 0x11
VK_W = 0x57
KEYEVENTF_KEYUP = 0x0002

CREATE_NO_WINDOW = 0x08000000
WM_CLOSE = 0x0010
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_CLOAKED = 14

# Shell/system surfaces that "close X" must never touch.
_SHELL_PROCESSES = {
    "shellexperiencehost.exe", "startmenuexperiencehost.exe", "searchhost.exe",
    "searchapp.exe", "textinputhost.exe", "lockapp.exe", "systemsettingsbroker.exe",
}
_SHELL_TITLES = {"program manager"}


def _powershell(script: str, timeout: float = 20.0) -> str:
    encoded = base64.b64encode(
        ("[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + script)
        .encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
         "Bypass", "-EncodedCommand", encoded],
        capture_output=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=CREATE_NO_WINDOW)
    return result.stdout


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

    # ---- apps (Start menu catalog: classic + Store apps) ----

    def list_apps(self) -> list[dict[str, str]]:
        try:
            return parse_start_apps_json(
                _powershell("Get-StartApps | ConvertTo-Json -Compress"))
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error("list_apps failed: %s", exc)
            return []

    def launch_app(self, app_id: str) -> bool:
        try:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"],
                             creationflags=CREATE_NO_WINDOW)
            return True
        except OSError as exc:
            logger.error("launch_app failed: %s", exc)
            return False

    # ---- running app windows (polite close only) ----

    def list_windows(self) -> list[dict[str, Any]]:
        import psutil

        own_pid = os.getpid()
        dwmapi = ctypes.windll.dwmapi
        found: list[dict[str, Any]] = []
        enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND,
                                       ctypes.wintypes.LPARAM)

        def visit(hwnd, _lparam):
            u = self._user32
            if not u.IsWindowVisible(hwnd) or u.GetWindow(hwnd, GW_OWNER):
                return True
            if u.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            cloaked = ctypes.c_int(0)
            dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked),
                                         ctypes.sizeof(cloaked))
            if cloaked.value:
                return True  # suspended Store apps / other virtual desktops
            length = u.GetWindowTextLengthW(hwnd)
            if not length:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            u.GetWindowTextW(hwnd, buf, length + 1)
            pid = ctypes.wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == own_pid:
                return True
            try:
                process_name = psutil.Process(pid.value).name()
            except Exception:
                return True
            if (process_name.lower() in _SHELL_PROCESSES
                    or buf.value.strip().lower() in _SHELL_TITLES):
                return True
            found.append({"hwnd": int(hwnd), "pid": int(pid.value),
                          "process_name": process_name, "title": buf.value})
            return True

        self._user32.EnumWindows(enum_proc(visit), 0)
        return found

    def close_window(self, hwnd: int) -> bool:
        # WM_CLOSE = clicking the window's X: the app may still ask to save.
        return bool(self._user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))

    # ---- settings pages / URIs ----

    def open_uri(self, uri: str) -> bool:
        try:
            os.startfile(uri)  # noqa: S606 - fixed ms-settings: URIs only
            return True
        except OSError as exc:
            logger.error("open_uri failed: %s", exc)
            return False
