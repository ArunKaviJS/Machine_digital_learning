"""Pure classification/parsing helpers shared by the OS adapter, tracker and guard.

No ctypes, no I/O → trivially unit-testable.
"""

from __future__ import annotations

import json


def normalize(name: str | None) -> str:
    return (name or "").strip().lower()


def friendly_app_name(process_name: str | None) -> str:
    """'chrome.exe' -> 'Chrome'; 'Code' -> 'Code'."""
    name = normalize(process_name)
    if name.endswith(".exe"):
        name = name[:-4]
    return name.capitalize() if name else "Unknown"


def is_browser(process_name: str | None, browsers: list[str]) -> bool:
    return normalize(process_name) in {normalize(b) for b in browsers}


def match_site(title: str | None, site_matchers: dict[str, list[str]]) -> str | None:
    """First tracked site whose title keyword appears in the window title."""
    if not title:
        return None
    lowered = title.lower()
    for site, keywords in (site_matchers or {}).items():
        for keyword in keywords:
            if keyword.lower() in lowered:
                return site
    return None


def is_dnd_app(process_name: str | None, dnd_apps: list[str]) -> bool:
    return normalize(process_name) in {normalize(a) for a in dnd_apps}


def classify(
    process_name: str | None,
    title: str | None,
    browsers: list[str],
    site_matchers: dict[str, list[str]],
) -> str | None:
    """website name if a browser shows a tracked site, else None."""
    if not is_browser(process_name, browsers):
        return None
    return match_site(title, site_matchers)


# ---- system-control output parsers (netsh / Get-StartApps; English locale) ----

def process_label(process_name: str | None) -> str:
    """'WhatsApp.Root.exe' -> 'WhatsApp.Root'."""
    name = (process_name or "").strip()
    return name[:-4] if name.lower().endswith(".exe") else name


def app_identity(window: dict) -> tuple[str, str]:
    """(stable key, display name) for a running window. Store apps all run
    inside ApplicationFrameHost.exe, so for those the title is the identity."""
    label = process_label(window.get("process_name"))
    if label.lower() == "applicationframehost":
        title = (window.get("title") or "").strip()
        return f"title:{title.lower()}", title
    display = label.split(".")[0] or label  # 'WhatsApp.Root' -> 'WhatsApp'
    if display.islower():                   # 'explorer' -> 'Explorer',
        display = " ".join(w.capitalize()   # 'ms-teams' -> 'Ms Teams'
                           for w in display.replace("_", "-").split("-") if w)
    return f"proc:{label.lower()}", display


def parse_start_apps_json(text: str) -> list[dict[str, str]]:
    """`Get-StartApps | ConvertTo-Json` -> [{'name', 'app_id'}] (one app = dict)."""
    try:
        data = json.loads(text or "null")
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    apps = []
    for item in data or []:
        if isinstance(item, dict) and item.get("Name") and item.get("AppID"):
            apps.append({"name": str(item["Name"]), "app_id": str(item["AppID"])})
    return apps
