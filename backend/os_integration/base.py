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
