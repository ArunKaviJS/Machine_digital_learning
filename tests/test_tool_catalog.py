"""Tool catalog: role/when-to-use prompt, Windows 11 shortcuts, per-app
actions — and that nothing risky (power, lock, credentials, Run box, Task
Manager, permanent delete, sending messages) is in any list."""

from __future__ import annotations

import pytest

from ai.agent_prompts import AGENT_TOOLS, CHAT_TOOLS, build_agent_messages, step_schema
from ai.tool_catalog import (APP_ACTIONS, TOOL_SPECS, WINDOWS_SHORTCUTS, actions_for,
                             app_for_process)
from backend.os_integration.windows import VK_CODES
from backend.services.agent_service import AgentTools, grounded, needs_agent
from tests.fakes import FakeOSAdapter

FORBIDDEN_COMBOS = [
    ["win", "l"], ["win", "r"], ["win", "x"], ["ctrl", "alt", "delete"],
    ["ctrl", "shift", "escape"], ["alt", "f4"], ["shift", "delete"], ["win", "u"],
]


def _all_key_lists():
    for keys, *_ in WINDOWS_SHORTCUTS.values():
        yield keys
    for app in [None, *APP_ACTIONS]:
        for keys, _what in actions_for(app).values():
            yield keys


def test_every_tool_has_role_when_and_input_and_is_in_the_prompt():
    prompt = build_agent_messages(chat=True)[0]["content"]
    for spec in TOOL_SPECS:
        assert spec["role"] and spec["when"] and "input" in spec
        assert f"- {spec['name']}: {spec['role']}. Use when: {spec['when']}" in prompt
    for name in WINDOWS_SHORTCUTS:
        assert name in prompt
    assert "ask_user" in CHAT_TOOLS and "ask_user" not in AGENT_TOOLS
    assert set(step_schema(True)["properties"]["action"]["enum"]) == set(CHAT_TOOLS)


def test_no_power_lock_credential_or_run_shortcuts_anywhere():
    for keys in _all_key_lists():
        assert keys not in FORBIDDEN_COMBOS, keys
    names = " ".join(list(WINDOWS_SHORTCUTS) + [a for app in [None, *APP_ACTIONS]
                                                 for a in actions_for(app)])
    for bad in ("lock", "shutdown", "shut_down", "restart", "sleep", "sign_out", "logoff",
                "password", "credential", "task_manager", "run_box", "delete", "send"):
        assert bad not in names, bad


def test_every_key_in_the_catalog_can_actually_be_pressed():
    for keys in _all_key_lists():
        for k in keys:
            assert k in VK_CODES, k


def test_app_lookup_by_process():
    assert app_for_process("chrome.exe") == "browser"
    assert app_for_process("Notepad.exe") == "notepad"
    assert app_for_process("unknown.exe") is None
    assert "copy" in actions_for(None) and "new_tab" in actions_for("browser")


# ---- the tools ---------------------------------------------------------------

@pytest.fixture()
def chrome():
    fake = FakeOSAdapter()
    win = {"hwnd": 60, "pid": 6, "process_name": "chrome.exe", "title": "Google Chrome"}
    fake.windows = [win]
    fake.foreground = win
    tools = AgentTools(fake, sleep=lambda _s: None)
    tools.active = win
    return fake, tools


def test_app_actions_observes_what_the_app_can_do(chrome):
    fake, tools = chrome
    ok, obs, _ = tools.run("app_actions", "")
    assert ok and "new_tab = open a new tab" in obs and "How to use:" in obs
    assert fake.keys_sent == []                     # observing presses nothing


def test_app_action_presses_the_catalog_keys(chrome):
    fake, tools = chrome
    ok, obs, _ = tools.run("app_action", "new tab")
    assert ok and fake.keys_sent == [["ctrl", "t"]] and obs == "open a new tab in chrome."


def test_app_action_unknown_suggests_observing(chrome):
    fake, tools = chrome
    ok, obs, _ = tools.run("app_action", "hack_the_planet")
    assert not ok and "app_actions" in obs and fake.keys_sent == []


def test_windows_shortcut_and_unknown_name(chrome):
    fake, tools = chrome
    ok, obs, _ = tools.run("windows_shortcut", "screenshot_snip")
    assert ok and fake.keys_sent == [["win", "shift", "s"]]
    ok, obs, _ = tools.run("windows_shortcut", "lock_screen")
    assert not ok and fake.keys_sent == [["win", "shift", "s"]]


def test_whatsapp_never_presses_enter():
    fake = FakeOSAdapter()
    wa = {"hwnd": 70, "pid": 7, "process_name": "WhatsApp.Root.exe", "title": "WhatsApp"}
    fake.windows, fake.foreground = [wa], wa
    tools = AgentTools(fake, sleep=lambda _s: None)
    tools.active = wa
    ok, obs, _ = tools.run("press_key", "enter")
    assert not ok and "send" in obs and fake.keys_sent == []
    ok, _, _ = tools.run("type_text", "hi\nthere")
    assert ok and fake.typed == ["hi there"]        # newline would have sent it


# ---- routing + grounding -----------------------------------------------------

@pytest.mark.parametrize("text", ["take a screenshot", "show desktop", "open emoji panel",
                                  "open a new tab", "make it bold", "volume up",
                                  "snap this window left"])
def test_feature_requests_go_to_the_agent(text):
    assert needs_agent(text)


@pytest.mark.parametrize("text", ["tidy my downloads", "open notepad", "how much youtube today"])
def test_other_requests_dont(text):
    assert not needs_agent(text)


def test_grounding_for_catalog_tools():
    assert grounded("windows_shortcut", "screenshot_snip", "take a screenshot")
    assert not grounded("windows_shortcut", "screenshot_snip", "asdfghjkl")
    assert grounded("app_action", "new_tab", "open a new tab in chrome")
    assert grounded("app_action", "refresh", "reload the page")
    assert not grounded("app_action", "new_tab", "how are you")
    assert grounded("app_actions", "", "anything")    # observing is always fine


def test_one_part_request_finishes_after_the_action_works(chrome):
    """Live: the model pressed volume_up, then kept trying keys and said it
    was stuck. One successful catalog action ends a one-part job."""
    from backend.services.agent_service import AgentService
    from tests.test_agent import CFG, ScriptedClient, s
    fake, tools = chrome
    client = ScriptedClient([s("windows_shortcut", "volume_up"),
                             s("press_key", "volume_up"), s("finish", "copied example")])
    agent = AgentService(None, CFG, fake, client=client, tools=tools)
    resp = agent.run("volume up")
    assert fake.keys_sent == [["volume_up"]] and len(client.calls) == 1
    assert resp["text"] == "Done, bro — volume up a step." and resp["animation"] == "success"


def test_multi_part_request_keeps_going_after_an_action(chrome):
    from backend.services.agent_service import AgentService
    from tests.test_agent import CFG, ScriptedClient, s
    fake, tools = chrome
    client = ScriptedClient([s("app_action", "new_tab"), s("type_text", "youtube.com"),
                             s("finish", "Opened a tab and typed it, bro.")])
    agent = AgentService(None, CFG, fake, client=client, tools=tools)
    resp = agent.run("open a new tab and type youtube.com")
    assert fake.keys_sent == [["ctrl", "t"]] and fake.typed == ["youtube.com"]
    assert resp["text"] == "Opened a tab and typed it, bro."
