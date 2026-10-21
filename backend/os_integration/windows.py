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

VK_MENU = 0x12
VK_F24 = 0x87  # no app binds it: a harmless "last input" for focus changes
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
SW_RESTORE = 9
SW_MINIMIZE = 6
SW_MAXIMIZE = 3

# agent key names -> virtual-key codes (the agent's whitelist decides which
# combos are allowed; this is only the name -> code table)
VK_CODES: dict[str, int] = {
    "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "backspace": 0x08,
    "delete": 0x2E, "space": 0x20, "up": 0x26, "down": 0x28, "left": 0x25,
    "right": 0x27, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "ctrl": VK_CONTROL, "shift": 0x10, "alt": VK_MENU,
    **{f"f{n}": 0x6F + n for n in range(1, 13)},
    # Windows-key shortcuts, punctuation used by app shortcuts, media keys
    "win": 0x5B, "printscreen": 0x2C,
    ".": 0xBE, ",": 0xBC, "=": 0xBB, "-": 0xBD, ";": 0xBA, "/": 0xBF, "\\": 0xDC,
    "volume_mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF,
    "media_next": 0xB0, "media_prev": 0xB1, "media_play_pause": 0xB3,
    **{chr(c): c for c in range(ord("0"), ord("9") + 1)},
    **{chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)},
}


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.wintypes.WORD), ("wScan", ctypes.wintypes.WORD),
                ("dwFlags", ctypes.wintypes.DWORD), ("time", ctypes.wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):  # only here so the union has the right size
    _fields_ = [("dx", ctypes.wintypes.LONG), ("dy", ctypes.wintypes.LONG),
                ("mouseData", ctypes.wintypes.DWORD), ("dwFlags", ctypes.wintypes.DWORD),
                ("time", ctypes.wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.wintypes.DWORD), ("u", _INPUTUNION)]


def _key_input(vk: int = 0, scan: int = 0, flags: int = 0) -> _INPUT:
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.u.ki = _KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    return inp

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


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("flags", ctypes.c_uint32),
                ("hwndActive", ctypes.c_void_p), ("hwndFocus", ctypes.c_void_p),
                ("hwndCapture", ctypes.c_void_p), ("hwndMenuOwner", ctypes.c_void_p),
                ("hwndMoveSize", ctypes.c_void_p), ("hwndCaret", ctypes.c_void_p),
                ("rcCaret", ctypes.c_long * 4)]


DWMWA_CAPTION_BUTTON_BOUNDS = 5
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
CAPTION_BUTTON_W, CAPTION_BUTTON_H = 46, 32   # Win 11 caption button at 100 %
TAB_CLOSE_X, TAB_CLOSE_Y = 235, 20            # ~first tab's X in Chrome/Edge/Notepad

READY_POLL_SECONDS = 0.1
READY_STABLE_POLLS = 4  # same focused control for ~0.4 s = the app is ready


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

    def set_window_state(self, hwnd: int, state: str) -> bool:
        """Same as the window's minimize / maximize button. (Win+Down on a
        maximized window only restores it: live, "minimize" left Calculator
        normal-sized.)"""
        command = {"minimize": SW_MINIMIZE, "maximize": SW_MAXIMIZE}.get(state)
        if command is None or not self._user32.IsWindow(hwnd):
            return False
        self._user32.ShowWindow(hwnd, command)
        return True

    def caption_button_point(self, hwnd: int, kind: str) -> tuple[int, int] | None:
        """Centre of the window's minimize / maximize / close button (DWM's
        caption-button bounds; standard Win 11 sizes if the app draws its
        own title bar), or roughly the first tab's X for close_tab."""
        index = {"minimize": 0, "maximize": 1, "close": 2}.get(kind)
        if index is None and kind != "close_tab":
            return None
        u = self._user32
        if not u.IsWindow(hwnd) or u.IsIconic(hwnd):
            return None
        # DWM reports physical pixels; read the window rect in physical pixels
        # too (a DPI-unaware thread gets scaled ones: x=1890 on a window
        # ending at 1543 at 125 %). The client converts to its own units.
        set_ctx = u.SetThreadDpiAwarenessContext
        set_ctx.restype = ctypes.c_void_p
        set_ctx.argtypes = [ctypes.c_void_p]
        old = set_ctx(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        try:
            return self._caption_point(hwnd, kind, index)
        finally:
            set_ctx(old)

    def _caption_point(self, hwnd: int, kind: str, index: int | None) -> tuple[int, int] | None:
        u = self._user32
        rect = ctypes.wintypes.RECT()
        if not u.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        scale = (u.GetDpiForWindow(hwnd) or 96) / 96
        top = max(rect.top, 0)  # maximized windows start a few px above 0
        if kind == "close_tab":  # tab strips are app-drawn: first tab's X
            return rect.left + int(TAB_CLOSE_X * scale), top + int(TAB_CLOSE_Y * scale)
        bounds = ctypes.wintypes.RECT()
        got = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_CAPTION_BUTTON_BOUNDS, ctypes.byref(bounds),
            ctypes.sizeof(bounds)) == 0 and bounds.right - bounds.left > 0
        if got:
            third = (bounds.right - bounds.left) / 3
            x = rect.left + bounds.left + third * (index + 0.5)
            y = rect.top + (bounds.top + bounds.bottom) / 2
        else:  # app-drawn title bar: measure from the VISIBLE frame, not the
            # invisible resize border (9 px further out at 125 %)
            visible = ctypes.wintypes.RECT()
            if ctypes.windll.dwmapi.DwmGetWindowAttribute(
                    hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(visible),
                    ctypes.sizeof(visible)) == 0 and visible.right > visible.left:
                rect, top = visible, max(visible.top, 0)
            width = CAPTION_BUTTON_W * scale
            x = rect.right - width * (3 - index - 0.5)
            y = top + CAPTION_BUTTON_H * scale / 2
        return int(x), int(max(y, 1))

    # ---- settings pages / URIs ----

    def open_uri(self, uri: str) -> bool:
        try:
            os.startfile(uri)  # noqa: S606 - fixed ms-settings: URIs only
            return True
        except OSError as exc:
            logger.error("open_uri failed: %s", exc)
            return False

    # ---- agent hands: focus / type / keys (SendInput, no admin rights) ----

    def focus_window(self, hwnd: int) -> bool:
        u = self._user32
        if not u.IsWindow(hwnd):
            return False
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, SW_RESTORE)
        # Windows only lets the process that got the last input steal focus;
        # a synthetic key tap counts as input, so SetForegroundWindow works.
        # F24, not Alt: a lone Alt tap puts Win 11 Notepad (and most apps)
        # into menu mode, which ate the first typed letters as shortcuts.
        u.keybd_event(VK_F24, 0, 0, 0)
        u.keybd_event(VK_F24, 0, KEYEVENTF_KEYUP, 0)
        u.SetForegroundWindow(hwnd)
        if int(u.GetForegroundWindow() or 0) == int(hwnd):
            return True
        # fallback: share the current foreground thread's input state, which
        # lifts the foreground lock for this call
        fg = u.GetForegroundWindow()
        fg_thread = u.GetWindowThreadProcessId(fg, None) if fg else 0
        me = self._kernel32.GetCurrentThreadId()
        attached = bool(fg_thread and fg_thread != me
                        and u.AttachThreadInput(me, fg_thread, True))
        try:
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
        finally:
            if attached:
                u.AttachThreadInput(me, fg_thread, False)
        return int(u.GetForegroundWindow() or 0) == int(hwnd)

    def _send(self, inputs: list[_INPUT]) -> bool:
        if not inputs:
            return True
        arr = (_INPUT * len(inputs))(*inputs)
        sent = self._user32.SendInput(len(inputs), arr, ctypes.sizeof(_INPUT))
        return sent == len(inputs)

    def _focused_control(self, hwnd: int) -> int:
        """The control holding keyboard focus in `hwnd`'s UI thread (0 if none)."""
        info = _GUITHREADINFO()
        info.cbSize = ctypes.sizeof(_GUITHREADINFO)
        thread = self._user32.GetWindowThreadProcessId(hwnd, None)
        if not thread or not self._user32.GetGUIThreadInfo(thread, ctypes.byref(info)):
            return 0
        return int(info.hwndFocus or 0)

    def wait_ready(self, hwnd: int, timeout: float = 4.0) -> bool:
        """Block until `hwnd` is in front AND its keyboard focus has settled
        on one control for a moment. A just-opened app (Win 11 Notepad) is
        in front before its text box can take keys; letters typed in that
        window were dropped ("i love you" -> " love you")."""
        import time

        deadline = time.monotonic() + timeout
        last, stable = 0, 0
        while time.monotonic() < deadline:
            if int(self._user32.GetForegroundWindow() or 0) != int(hwnd):
                last, stable = 0, 0
            else:
                focus = self._focused_control(hwnd)
                stable = stable + 1 if focus and focus == last else 0
                last = focus
                if stable >= READY_STABLE_POLLS:
                    return True
            time.sleep(READY_POLL_SECONDS)
        return int(self._user32.GetForegroundWindow() or 0) == int(hwnd)

    def type_text(self, text: str, hwnd: int | None = None) -> bool:
        import time

        try:
            ok = True
            for ch in text:
                if hwnd is not None and int(self._user32.GetForegroundWindow() or 0) != int(hwnd):
                    logger.warning("type_text stopped: target window lost focus")
                    return False
                if ch == "\n":
                    vk = VK_CODES["enter"]
                    ok &= self._send([_key_input(vk), _key_input(vk, flags=KEYEVENTF_KEYUP)])
                    continue
                units = ch.encode("utf-16-le")  # surrogate pairs for emoji
                inputs = []
                for i in range(0, len(units), 2):
                    code = int.from_bytes(units[i:i + 2], "little")
                    inputs += [_key_input(scan=code, flags=KEYEVENTF_UNICODE),
                               _key_input(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
                ok &= self._send(inputs)
                time.sleep(0.01)  # slow apps drop keys sent in one burst
            return bool(ok)
        except Exception as exc:
            logger.error("type_text failed: %s", exc)
            return False

    def send_keys(self, keys: list[str]) -> bool:
        try:
            codes = [VK_CODES[k] for k in keys]
        except KeyError:
            return False
        down = [_key_input(vk) for vk in codes]
        up = [_key_input(vk, flags=KEYEVENTF_KEYUP) for vk in reversed(codes)]
        try:
            return self._send(down + up)
        except Exception as exc:
            logger.error("send_keys failed: %s", exc)
            return False
