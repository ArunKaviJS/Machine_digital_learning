"""Pure classification helpers shared by the OS adapter, tracker and guard.

No ctypes, no I/O → trivially unit-testable.
"""

from __future__ import annotations


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
