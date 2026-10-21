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

    def set_window_state(self, hwnd: int, state: str) -> bool:
        """Minimize / maximize one window directly (like its caption
        button). False if unsupported — callers then send the shortcut."""
        return False

    def caption_button_point(self, hwnd: int, kind: str) -> tuple[int, int] | None:
        """Screen point of a window's caption button — kind = close /
        maximize / minimize, or close_tab (estimated) — so the character can
        walk there. None if unknown."""
        return None

    @abstractmethod
    def close_window(self, hwnd: int) -> bool:
        """Politely ask a window to close (same as clicking its X) — the app
        can still prompt to save. Never force-kills. True if the request was
        delivered."""

    @abstractmethod
    def open_uri(self, uri: str) -> bool:
        """Open a URI such as ms-settings:display. True if started."""

    # ---- agent hands: focus a window, type, press keys (no admin rights) ----

    @abstractmethod
    def focus_window(self, hwnd: int) -> bool:
        """Restore + bring a window to the front. True if it is now foreground."""

    @abstractmethod
    def type_text(self, text: str, hwnd: int | None = None) -> bool:
        """Type unicode text into the foreground window. With `hwnd`, stop as
        soon as that window is no longer in front (keys must never land in
        another app). True if all of it was sent."""

    def wait_ready(self, hwnd: int, timeout: float = 2.0) -> bool:
        """Block until `hwnd` is in front and can take keys. True if ready."""
        return True

    @abstractmethod
    def send_keys(self, keys: list[str]) -> bool:
        """Press a key combo, e.g. ['ctrl', 's'] or ['enter'], in the
        foreground window. Names come from the agent's whitelist. True if sent."""
