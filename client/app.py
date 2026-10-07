"""Qt app entry (SKILL §20, M11). Single-instance guarded."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import QApplication

from client.api_client import ApiClient
from client.character_window import CharacterWindow
from client.hotkey import GlobalHotkey
from client.single_instance import SingleInstanceLock
from client.tray import BroTray

logger = logging.getLogger("arun.client")


def _lock_path() -> Path:
    import os

    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "Arun" / "arun.lock"


def run_client(config: dict[str, Any]) -> int:
    lock = SingleInstanceLock(_lock_path())
    if not lock.acquire():
        logger.warning("Arun is already running (single-instance lock held); exiting.")
        return 0

    app = QApplication(sys.argv)
    # CharacterWindow/SpeechBubble are Qt.WindowType.Tool, so Qt doesn't count
    # them toward "last window closed" — but a normal dialog (e.g. the "Ask
    # Bro..." QInputDialog) does. Without this, closing that dialog silently
    # quits the whole app; only the explicit Quit menu action should exit.
    app.setQuitOnLastWindowClosed(False)

    api = ApiClient(config)
    window = CharacterWindow(config, api_client=api)

    hotkey_text = config.get("callHotkey", "Ctrl+Alt+B")
    tray = BroTray(hotkey_text)
    tray.call.connect(window.toggle)
    tray.quit_requested.connect(window.quit_app)
    tray.show()
    hotkey = GlobalHotkey(hotkey_text)
    hotkey.pressed.connect(window.toggle)
    hotkey.start()

    if config.get("presence", "on_demand") == "always":
        window.show()
    else:
        tray.notify("Bro is in your tray",
                    f"Click the droplet or press {hotkey_text} when you need me. "
                    "I'll pop up by myself for reminders.")

    try:
        return app.exec()
    finally:
        hotkey.stop()
        tray.hide()
        lock.release()
