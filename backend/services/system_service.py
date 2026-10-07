"""Open Windows Settings pages (SKILL §7 action handlers).

Open-only by design: nothing here changes a system setting or needs admin
rights. Things Windows offers no app API for (e.g. Night light) open their
Settings page instead of being toggled via undocumented registry hacks.
"""

from __future__ import annotations

import re
from typing import Any

# Windows Settings deep links. Keys are matched against the user's words.
SETTINGS_PAGES: dict[str, str] = {
    "night light": "ms-settings:nightlight",
    "blue light": "ms-settings:nightlight",
    "display": "ms-settings:display",
    "brightness": "ms-settings:display",
    "resolution": "ms-settings:display",
    "bluetooth": "ms-settings:bluetooth",
    "wifi": "ms-settings:network-wifi",
    "network": "ms-settings:network",
    "internet": "ms-settings:network",
    "hotspot": "ms-settings:network-mobilehotspot",
    "vpn": "ms-settings:network-vpn",
    "sound": "ms-settings:sound",
    "volume": "ms-settings:sound",
    "battery": "ms-settings:batterysaver",
    "power": "ms-settings:powersleep",
    "notifications": "ms-settings:notifications",
    "apps": "ms-settings:appsfeatures",
    "windows update": "ms-settings:windowsupdate",
    "update": "ms-settings:windowsupdate",
    "storage": "ms-settings:storagesense",
    "mouse": "ms-settings:mousetouchpad",
    "touchpad": "ms-settings:devices-touchpad",
    "keyboard": "ms-settings:typing",
    "printer": "ms-settings:printers",
    "privacy": "ms-settings:privacy",
    "date": "ms-settings:dateandtime",
    "time": "ms-settings:dateandtime",
    "language": "ms-settings:regionlanguage",
    "wallpaper": "ms-settings:personalization-background",
    "background": "ms-settings:personalization-background",
    "theme": "ms-settings:themes",
    "dark mode": "ms-settings:colors",
    "colors": "ms-settings:colors",
    "color": "ms-settings:colors",
    "colours": "ms-settings:colors",
    "colour": "ms-settings:colors",
}
GENERAL_SETTINGS = "ms-settings:"


def settings_page(target: str | None) -> tuple[str, str]:
    """(label, uri) for a spoken settings target; unknown -> general Settings."""
    if target:
        t = re.sub(r"[^a-z0-9 ]+", " ", target.lower())
        t = re.sub(r"\bwi ?fi\b", "wifi", t)
        t = re.sub(r"\bsettings?\b", " ", t).strip()
        for key in sorted(SETTINGS_PAGES, key=len, reverse=True):
            if re.search(rf"\b{re.escape(key)}\b", t):
                return key, SETTINGS_PAGES[key]
    return "settings", GENERAL_SETTINGS


class SystemService:
    def __init__(self, os_adapter):
        self.os = os_adapter

    def open_settings(self, target: str | None) -> dict[str, Any]:
        label, uri = settings_page(target)
        ok = self.os is not None and self.os.open_uri(uri)
        return {"status": "opened" if ok else "error", "page": label}
