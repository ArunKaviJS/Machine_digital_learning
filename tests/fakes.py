"""Fake OS adapter for tests: scriptable, records calls, no ctypes."""

from __future__ import annotations

from typing import Any

from backend.os_integration.base import OSAdapter


class FakeOSAdapter(OSAdapter):
    def __init__(
        self,
        foreground: dict[str, Any] | None = None,
        idle_seconds: float = 0.0,
        dnd: bool = False,
    ):
        self.foreground = foreground
        self.idle_seconds = idle_seconds
        self.dnd = dnd
        self.close_tab_calls = 0
        self.autostart: bool | None = None
        self.close_tab_result = True
        # system control (scriptable)
        self.apps: list[dict[str, str]] = []
        self.launched: list[str] = []
        self.windows: list[dict[str, Any]] = []
        self.closed: list[int] = []
        self.opened_uris: list[str] = []

    def get_foreground_window(self) -> dict[str, Any] | None:
        return self.foreground

    def get_idle_seconds(self) -> float:
        return self.idle_seconds

    def is_dnd_active(self) -> bool:
        return self.dnd

    def send_close_tab(self) -> bool:
        self.close_tab_calls += 1
        return self.close_tab_result

    def set_autostart(self, enabled: bool) -> None:
        self.autostart = enabled

    def list_apps(self) -> list[dict[str, str]]:
        return list(self.apps)

    def launch_app(self, app_id: str) -> bool:
        self.launched.append(app_id)
        return True

    def list_windows(self) -> list[dict[str, Any]]:
        return [w for w in self.windows if w["hwnd"] not in self.closed]

    def close_window(self, hwnd: int) -> bool:
        self.closed.append(hwnd)
        return True

    def open_uri(self, uri: str) -> bool:
        self.opened_uris.append(uri)
        return True


def fg(process_name: str, title: str = "", pid: int = 1, hwnd: int = 1) -> dict[str, Any]:
    """Shorthand for a fake foreground window dict."""
    return {"hwnd": hwnd, "pid": pid, "process_name": process_name, "title": title}
