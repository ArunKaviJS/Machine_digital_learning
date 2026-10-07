"""Open/close apps and Settings pages: matching, services, router (no real OS)."""

from __future__ import annotations

import pytest

from backend.db.connection import Database
from backend.db.migrations import migrate
from backend.os_integration.helpers import parse_start_apps_json
from backend.router.router import QuestionRouter
from backend.services.app_launcher_service import (
    AppLauncherService,
    best_app_in_text,
    best_app_match,
    clear_app_cache,
)
from backend.services.system_service import GENERAL_SETTINGS, settings_page
from tests.fakes import FakeOSAdapter

APPS = [
    {"name": "WhatsApp", "app_id": "5319275A.WhatsAppDesktop!App"},
    {"name": "Notepad", "app_id": "Microsoft.WindowsNotepad!App"},
    {"name": "Google Chrome", "app_id": "Chrome"},
    {"name": "Settings", "app_id": "windows.immersivecontrolpanel!settings"},
    {"name": "WSL Settings", "app_id": "wsl-settings"},
    {"name": "Calculator", "app_id": "Microsoft.WindowsCalculator!App"},
    {"name": "Visual Studio Code", "app_id": "Microsoft.VisualStudioCode"},
    {"name": "Uninstall Chrome Helper", "app_id": "uninstall-helper"},
    {"name": "Photos", "app_id": "Microsoft.Windows.Photos!App"},
]

CFG = {
    "siteMatchers": {"youtube.com": ["YouTube"], "instagram.com": ["Instagram"]},
    "distractingSites": ["youtube.com", "instagram.com"],
    "browsers": ["chrome.exe"],
    "waterDailyTarget": 8,
}


@pytest.fixture(autouse=True)
def _fresh_app_cache():
    clear_app_cache()
    yield
    clear_app_cache()


@pytest.fixture()
def fake():
    adapter = FakeOSAdapter()
    adapter.apps = list(APPS)
    return adapter


# ---- matching ----

@pytest.mark.parametrize("query,expected", [
    ("whatsapp", "WhatsApp"),
    ("WhatsApp", "WhatsApp"),
    ("notepad", "Notepad"),
    ("chrome", "Google Chrome"),          # word match beats the noisy "Uninstall ..."
    ("settings", "Settings"),             # exact beats "WSL Settings"
    ("calc", "Calculator"),               # substring
    ("vsc", "Visual Studio Code"),        # initials
    ("code", "Visual Studio Code"),
    ("photoshop", None),                  # not installed — must NOT open "Photos"
    ("whatsap", "WhatsApp"),              # typo
    ("notpad", "Notepad"),                # typo
    ("calculater", "Calculator"),         # typo
    ("", None),
])
def test_best_app_match(query, expected):
    match = best_app_match(query, APPS)
    assert (match["name"] if match else None) == expected


@pytest.mark.parametrize("query", ["vscode", "vs code", "vsc", "visual studio code"])
def test_abbreviations(query):
    assert best_app_match(query, APPS)["name"] == "Visual Studio Code"


@pytest.mark.parametrize("sentence,expected", [
    ("bring my calculator", "Calculator"),
    ("I need to message my friends on whatsapp", "WhatsApp"),
    ("could you start up vs code for me", "Visual Studio Code"),
    ("tell me a joke", None),
    ("please open something nice", None),  # no fuzzy guessing from stray words
])
def test_best_app_in_text(sentence, expected):
    match = best_app_in_text(sentence, APPS)
    assert (match["name"] if match else None) == expected


def test_open_app_finds_app_named_inside_a_sentence(fake):
    result = AppLauncherService(fake).open_app("bring my calculator")
    assert result["status"] == "opened" and result["name"] == "Calculator"


def test_close_sentence_fallback_matches_process_not_loose_title_words(fake):
    fake.windows = [_win(1, "WhatsApp.Root.exe", "WhatsApp"),
                    _win(2, "chrome.exe", "Notes about the whatsapp window - Chrome")]
    result = AppLauncherService(fake).close_app("get rid of the whatsapp window")
    assert result["status"] == "closed" and fake.closed == [1]


def test_gateway_uses_users_words_when_ai_drops_the_app_name():
    import json

    from backend.services.ai_gateway import OllamaGateway
    gw = OllamaGateway.__new__(OllamaGateway)
    gw.config = CFG
    response = {"message": {"content": json.dumps(
        {"intent": "open_app", "application": "any"})}}
    intent = gw._validate(response, "bring my calculator")
    assert intent["intent"] == "open_app" and intent["target"] == "bring my calculator"
    # other intents are untouched: no target invented for them
    bad = {"message": {"content": json.dumps({"intent": "usage_query"})}}
    assert gw._validate(bad, "whatever") is None


def test_parse_start_apps_json_handles_single_object_and_garbage():
    assert parse_start_apps_json('{"Name": "Notepad", "AppID": "np"}') == \
        [{"name": "Notepad", "app_id": "np"}]
    assert parse_start_apps_json('[{"Name": "A", "AppID": "a"}, {"Name": ""}]') == \
        [{"name": "A", "app_id": "a"}]
    assert parse_start_apps_json("not json") == []


# ---- open ----

def test_open_app_launches_matched_app(fake):
    result = AppLauncherService(fake).open_app("whatsapp")
    assert result == {"status": "opened", "query": "whatsapp", "name": "WhatsApp"}
    assert fake.launched == ["5319275A.WhatsAppDesktop!App"]


def test_open_app_not_installed(fake):
    result = AppLauncherService(fake).open_app("photoshop")
    assert result["status"] == "not_found"
    assert fake.launched == []


def test_open_app_domain_falls_back_to_browser(fake, monkeypatch):
    opened = []
    monkeypatch.setattr(AppLauncherService, "open_site",
                        lambda self, site: opened.append(site) or True)
    result = AppLauncherService(fake).open_app("github.com")
    assert result["status"] == "opened_url" and opened == ["github.com"]


def test_app_catalog_is_cached(fake):
    calls = []
    original = fake.list_apps
    fake.list_apps = lambda: calls.append(1) or original()
    svc = AppLauncherService(fake)
    svc.open_app("notepad")
    svc.open_app("whatsapp")
    assert len(calls) == 1


# ---- close ----

def _win(hwnd, process, title):
    return {"hwnd": hwnd, "pid": hwnd, "process_name": process, "title": title}


def test_close_app_closes_all_windows_of_best_match_only(fake):
    fake.windows = [
        _win(1, "Notepad.exe", "notes.txt - Notepad"),
        _win(2, "Notepad.exe", "todo.txt - Notepad"),
        _win(3, "chrome.exe", "Notepad tips - Google Chrome"),  # weaker: title only
    ]
    result = AppLauncherService(fake).close_app("notepad")
    assert result["status"] == "closed" and result["count"] == 2
    assert fake.closed == [1, 2]


def test_close_store_app_matched_by_title(fake):
    fake.windows = [_win(7, "ApplicationFrameHost.exe", "Calculator")]
    result = AppLauncherService(fake).close_app("calculator")
    assert result["status"] == "closed" and result["name"] == "Calculator"
    assert fake.closed == [7]


def test_close_app_not_running(fake):
    fake.windows = [_win(1, "chrome.exe", "Inbox - Google Chrome")]
    result = AppLauncherService(fake).close_app("whatsapp")
    assert result["status"] == "not_running"
    assert fake.closed == []


# ---- settings ----

@pytest.mark.parametrize("target,label", [
    ("turn on night light", "night light"),
    ("open bluetooth settings", "bluetooth"),
    ("wi-fi settings", "wifi"),
    ("settings", "settings"),
    ("something unknown", "settings"),
    ("my eyes hurt from the blue light", "blue light"),
    ("i want to change my wallpaper", "wallpaper"),
    ("lower the brightness", "brightness"),
    ("change the colour", "colour"),
])
def test_settings_page(target, label):
    assert settings_page(target)[0] == label


def test_unknown_settings_target_opens_main_settings():
    assert settings_page(None) == ("settings", GENERAL_SETTINGS)


# ---- router end to end (rules -> service -> template) ----

@pytest.fixture()
def router(fake):
    db = Database(":memory:")
    migrate(db.raw)
    yield QuestionRouter(db, CFG, os_adapter=fake)
    db.close()


def test_router_open_installed_app(router, fake):
    resp = router.ask("can you open WhatsApp for me bro?")
    assert resp["text"] == "Opening WhatsApp for you, bro!"
    assert fake.launched == ["5319275A.WhatsAppDesktop!App"]


def test_router_open_missing_app_says_so(router, fake):
    resp = router.ask("open photoshop")
    assert "couldn't find an app called 'photoshop'" in resp["text"]
    assert fake.launched == []


def test_router_close_app(router, fake):
    fake.windows = [_win(5, "WhatsApp.exe", "WhatsApp")]
    resp = router.ask("close whatsapp")
    assert resp["text"].startswith("Closing WhatsApp")
    assert fake.closed == [5]


def test_router_night_light_opens_its_settings_page_honestly(router, fake):
    resp = router.ask("turn on night light")
    assert fake.opened_uris == ["ms-settings:nightlight"]
    assert "doesn't let apps flip it" in resp["text"]


def test_router_close_tracked_site_still_closes_the_tab_not_the_browser(router, fake):
    fake.foreground = {"process_name": "chrome.exe", "title": "YouTube - Google Chrome"}
    fake.windows = [_win(9, "chrome.exe", "YouTube - Google Chrome")]
    router.ask("close the youtube tab")
    assert fake.close_tab_calls == 1 and fake.closed == []
