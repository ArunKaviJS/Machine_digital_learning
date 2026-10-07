"""Tests for backend/os_integration: pure helpers + fake adapter wiring."""

from __future__ import annotations

import pytest

from backend.os_integration.factory import get_os_adapter
from backend.os_integration.helpers import (
    classify,
    friendly_app_name,
    is_browser,
    is_dnd_app,
    match_site,
)
from tests.fakes import FakeOSAdapter, fg

BROWSERS = ["chrome.exe", "msedge.exe", "firefox.exe"]
MATCHERS = {"youtube.com": ["YouTube"], "instagram.com": ["Instagram"]}
DND_APPS = ["zoom.exe", "teams.exe"]


# ---- helpers ----

@pytest.mark.parametrize(
    "process,title,expected",
    [
        ("chrome.exe", "... - YouTube - Google Chrome", "youtube.com"),
        ("msedge.exe", "Instagram - Google Chrome", "instagram.com"),
        ("chrome.exe", "GitHub - Where software is built", None),
        ("Code.exe", "main.py - YouTube?? no, VS Code", None),  # not a browser
        ("chrome.exe", None, None),
        (None, "YouTube", None),
        ("firefox.exe", "watch YouTube", "youtube.com"),
    ],
)
def test_classify(process, title, expected):
    assert classify(process, title, BROWSERS, MATCHERS) == expected


def test_match_site_is_case_insensitive_and_ordered():
    assert match_site("youtube - INSTAGRAM", MATCHERS) == "youtube.com"  # first match wins
    assert match_site("", MATCHERS) is None


@pytest.mark.parametrize("name", ["chrome.exe", "Chrome.EXE", " chrome.exe "])
def test_is_browser_normalizes(name):
    assert is_browser(name, BROWSERS)
    assert not is_browser("spotify.exe", BROWSERS)


def test_is_dnd_app():
    assert is_dnd_app("Zoom.exe", DND_APPS)
    assert is_dnd_app("teams.exe", DND_APPS)
    assert not is_dnd_app("chrome.exe", DND_APPS)


@pytest.mark.parametrize(
    "raw,expected",
    [("chrome.exe", "Chrome"), ("Code", "Code"), ("MS-TEAMS.exe", "Ms-teams"), (None, "Unknown")],
)
def test_friendly_app_name(raw, expected):
    assert friendly_app_name(raw) == expected


# ---- fake adapter ----

def test_fake_adapter_records_calls():
    fake = FakeOSAdapter(foreground=fg("chrome.exe", "YouTube"), idle_seconds=300, dnd=True)
    assert fake.get_foreground_window()["title"] == "YouTube"
    assert fake.get_idle_seconds() == 300
    assert fake.is_dnd_active() is True
    assert fake.send_close_tab() is True
    fake.set_autostart(True)
    assert fake.close_tab_calls == 1
    assert fake.autostart is True


def test_factory_returns_windows_adapter_on_win32():
    import sys

    if sys.platform != "win32":
        pytest.skip("Windows only")
    adapter = get_os_adapter({"dndApps": DND_APPS})
    assert adapter.dnd_apps == DND_APPS
