"""OS adapter interface (SKILL §22). Windows v1; macOS can implement later."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OSAdapter(ABC):
    """Everything the backend needs from the operating system."""

    @abstractmethod
    def get_foreground_window(self) -> dict[str, Any] | None:
        """{'hwnd','pid','process_name','title'} of the front window, or None."""

    @abstractmethod
    def get_idle_seconds(self) -> float:
        """Seconds since the last keyboard/mouse input."""

    @abstractmethod
    def is_dnd_active(self) -> bool:
        """True if notifications/meeting/fullscreen say 'do not disturb'."""

    @abstractmethod
    def send_close_tab(self) -> bool:
        """Send Ctrl+W to the foreground window. True if sent."""

    @abstractmethod
    def set_autostart(self, enabled: bool) -> None:
        """Add/remove the login entry for Arun."""

    # ---- open / close apps (no admin rights; decisions live in services) ----

    @abstractmethod
    def list_apps(self) -> list[dict[str, str]]:
        """Installed launchable apps: [{'name', 'app_id'}]."""

    @abstractmethod
    def launch_app(self, app_id: str) -> bool:
        """Launch an app from list_apps(). True if the launch was started."""

    @abstractmethod
    def list_windows(self) -> list[dict[str, Any]]:
        """Visible top-level app windows: [{'hwnd', 'pid', 'process_name',
        'title'}], excluding this process."""

    @abstractmethod
    def close_window(self, hwnd: int) -> bool:
        """Politely ask a window to close (same as clicking its X) — the app
        can still prompt to save. Never force-kills. True if the request was
        delivered."""

    @abstractmethod
    def open_uri(self, uri: str) -> bool:
        """Open a URI such as ms-settings:display. True if started."""
