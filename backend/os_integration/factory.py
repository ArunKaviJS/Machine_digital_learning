"""Choose the OS adapter for the current platform."""

from __future__ import annotations

import sys
from typing import Any

from backend.os_integration.base import OSAdapter


def get_os_adapter(config: dict[str, Any] | None = None) -> OSAdapter:
    cfg = config or {}
    if sys.platform == "win32":
        from backend.os_integration.windows import WindowsOSAdapter

        return WindowsOSAdapter(dnd_apps=cfg.get("dndApps", []))
    raise NotImplementedError(f"Arun v1 supports Windows only (got {sys.platform})")
