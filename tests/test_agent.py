"""Agent loop tests: scripted model steps, fake OS — no Ollama, no real input."""

from __future__ import annotations

import json

import pytest

from backend.db.connection import Database
from backend.db.migrations import migrate
from backend.router.router import CLARIFICATION, QuestionRouter
from backend.services import app_launcher_service
from backend.services.agent_service import (AgentService, AgentTools, grounded,
                                            needs_agent, parse_step)
from tests.fakes import FakeOSAdapter

CFG = {"ai": {"enabled": True, "agent": {"enabled": True, "maxSteps": 6}},
       "siteMatchers": {}, "distractingSites": []}


class ScriptedClient:
    """Returns one scripted step per chat() call; records the messages."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kwargs):
        self.calls.append(list(messages))
        if not self.steps:
            return None
        step = self.steps.pop(0)
        if step is None:
            return None
        return {"message": {"content": json.dumps(step)}}


def s(action, arg="", thought="t"):
    return {"thought": thought, "action": action, "input": arg}


class FakeSysInfo:
    def report(self, what="all"):
        return "OS: Windows 11 | RAM: 4.0 of 16.0 GB used (25%)"


@pytest.fixture(autouse=True)
def _clear_app_cache():
    app_launcher_service.clear_app_cache()
    yield
    app_launcher_service.clear_app_cache()


@pytest.fixture()
def os_adapter():
    fake = FakeOSAdapter()
    fake.apps = [{"name": "Notepad", "app_id": "notepad.id"},
                 {"name": "Calculator", "app_id": "calc.id"}]
    orig_launch = fake.launch_app

    def launch(app_id):  # launching makes the window appear
        if app_id == "notepad.id":
            fake.windows.append({"hwnd": 50, "pid": 5, "process_name": "Notepad.exe",
                                 "title": "Untitled - Notepad"})
        return orig_launch(app_id)

    fake.launch_app = launch
    return fake


@pytest.fixture()
def db():
    database = Database(":memory:")
    migrate(database.raw)
    yield database
    database.close()


def make_agent(db, os_adapter, steps, cfg=CFG):
    client = ScriptedClient(steps)
    tools = AgentTools(os_adapter, sysinfo=FakeSysInfo(), sleep=lambda _s: None)
    return AgentService(db, cfg, os_adapter, client=client, tools=tools), client


# ---- the user's two examples ---------------------------------------------

def test_open_notepad_and_write(db, os_adapter):
    agent, client = make_agent(db, os_adapter, [
        s("open_app", "notepad"), s("type_text", "how are you"),
        s("finish", "Opened Notepad and wrote it, bro.")])
    resp = agent.run("open notepad and write how are you")
    assert os_adapter.launched == ["notepad.id"]
    assert os_adapter.foreground["hwnd"] == 50  # typed into Notepad, not elsewhere
    assert os_adapter.typed == ["how are you"]
    assert resp["text"] == "Opened Notepad and wrote it, bro."
    assert resp["animation"] == "success"
    assert [st["action"] for st in resp["data"]["agent_steps"]] == ["open_app", "type_text"]
    # each observation is fed back to the model before the next step
    assert "Opened Notepad" in client.calls[1][-1]["content"]


def test_check_system_configuration_reads_specs(db, os_adapter):
    agent, _ = make_agent(db, os_adapter, [
        s("system_info", "all"), s("finish", "Here's your PC, bro.")])
    resp = agent.run("check the configuration of my system")
    assert os_adapter.opened_uris == []  # did NOT just open Settings and stop
    assert "RAM: 4.0 of 16.0 GB" in resp["text"]


def test_finish_without_typing_gets_nudged(db, os_adapter):
    agent, client = make_agent(db, os_adapter, [
        s("open_app", "notepad"), s("finish", "done"),  # forgot to type
        s("type_text", "how are you"), s("finish", "Done for real, bro.")])
    resp = agent.run("open notepad and write how are you")
    assert os_adapter.typed == ["how are you"]
    assert resp["text"] == "Done for real, bro."
    assert "nothing was typed" in client.calls[2][-1]["content"]


# ---- safety --------------------------------------------------------------

def test_ungrounded_actions_are_refused(db, os_adapter):
    """Small models copy the prompt examples for gibberish — never run them."""
    agent, _ = make_agent(db, os_adapter, [
        s("open_app", "notepad"), s("type_text", "hello world"), s("open_app", "notepad")])
    assert agent.run("asdfghjkl") is None  # nothing done -> router clarifies
    assert os_adapter.launched == [] and os_adapter.typed == []


def test_never_types_into_a_terminal(db, os_adapter):
    os_adapter.foreground = {"hwnd": 9, "pid": 9, "process_name": "WindowsTerminal.exe",
                             "title": "PowerShell"}
    os_adapter.windows = [os_adapter.foreground]
    agent, _ = make_agent(db, os_adapter, [s("type_text", "rm -rf"), s("finish", "ok"),
                                           s("finish", "Can't type there, bro.")])
    resp = agent.run("type rm -rf")
    assert os_adapter.typed == []
    assert resp["animation"] == "warn"


def test_press_key_whitelist(db, os_adapter):
    os_adapter.foreground = {"hwnd": 50, "pid": 5, "process_name": "Notepad.exe",
                             "title": "Notepad"}
    os_adapter.windows = [os_adapter.foreground]
    tools = AgentTools(os_adapter, sleep=lambda _s: None)
    assert tools.run("press_key", "ctrl+s")[0] is True
    assert tools.run("press_key", "Enter")[0] is True
    assert tools.run("press_key", "alt+f4")[0] is False
    assert tools.run("press_key", "win+r")[0] is False
    assert os_adapter.keys_sent == [["ctrl", "s"], ["enter"]]


def test_repeating_the_same_step_stops_the_loop(db, os_adapter):
    agent, client = make_agent(db, os_adapter, [s("system_info", "all")] * 6)
    resp = agent.run("check my pc specs")
    assert len(client.calls) == 3  # ran once, warned once, then stopped
    assert "RAM" in resp["text"]


def test_model_unreachable_returns_none(db, os_adapter):
    agent, _ = make_agent(db, os_adapter, [None])
    assert agent.run("open notepad and write hi") is None


def test_agent_disabled_by_config(db, os_adapter):
    cfg = {"ai": {"enabled": True, "agent": {"enabled": False}}}
    agent, client = make_agent(db, os_adapter, [s("finish", "x")], cfg=cfg)
    assert agent.run("open notepad and write hi") is None
    assert client.calls == []


def test_logs_one_ai_call(db, os_adapter):
    agent, _ = make_agent(db, os_adapter, [s("finish", "Hi bro!")])
    agent.run("hello there")
    row = db.raw.execute("SELECT intent, success FROM ai_calls").fetchone()
    assert tuple(row) == ("agent", 1)


# ---- pure helpers --------------------------------------------------------

@pytest.mark.parametrize("text", [
    "open notepad and write how are you",
    "open chrome then go to github",
    "type hello in notepad",
    "check the configuration of my system",
    "what are my pc specs",
    "how much ram do I have",
])
def test_needs_agent(text):
    assert needs_agent(text)


@pytest.mark.parametrize("text", [
    "open notepad", "how much youtube today", "close calculator",
    "tidy my downloads", "how much water did I drink",
])
def test_single_step_stays_on_rules(text):
    assert not needs_agent(text)


def test_grounded():
    task = "open vs code and write hello"
    assert grounded("open_app", "vscode", task)
    assert grounded("open_app", "vs code", task)
    assert not grounded("open_app", "notepad", task)
    assert grounded("type_text", "a poem about rain", "write a poem about rain")
    assert not grounded("type_text", "hello world", "asdfghjkl")
    assert grounded("system_info", "all", "how much ram do i have")
    assert not grounded("system_info", "all", "what is the meaning of life")


def test_parse_step_rejects_unknown_tools():
    assert parse_step({"message": {"content": '{"action": "run_shell", "input": "x"}'}}) is None
    assert parse_step({"message": {"content": "not json"}}) is None
    step = parse_step({"message": {"content": '{"action": "wait", "input": 3}'}})
    assert step == {"thought": "", "action": "wait", "input": "3"}


# ---- router wiring -------------------------------------------------------

class FakeAgent:
    def __init__(self, result):
        self.result = result
        self.calls: list[str] = []

    def run(self, text):
        self.calls.append(text)
        return self.result


def test_router_sends_multi_step_to_agent_before_rules(db):
    agent = FakeAgent({"text": "did it", "animation": "success",
                       "needs_confirmation": False, "proposal_id": None, "data": {}})
    router = QuestionRouter(db, CFG, agent=agent)
    assert router.ask("open notepad and write how are you")["text"] == "did it"
    assert agent.calls == ["open notepad and write how are you"]


def test_router_unknown_text_falls_back_to_agent_then_clarifies(db):
    agent = FakeAgent(None)
    router = QuestionRouter(db, CFG, agent=agent)
    assert router.ask("what is the meaning of life")["text"] == CLARIFICATION
    assert agent.calls == ["what is the meaning of life"]


# ---- run_command: fixed read-only commands in a terminal ------------------

@pytest.fixture()
def with_cmd(os_adapter):
    os_adapter.apps.append({"name": "Command Prompt", "app_id": "cmd.id"})
    orig = os_adapter.launch_app

    def launch(app_id):
        if app_id == "cmd.id":
            os_adapter.windows.append({"hwnd": 70, "pid": 7, "process_name": "cmd.exe",
                                       "title": "Command Prompt"})
        return orig(app_id)

    os_adapter.launch_app = launch
    return os_adapter


def test_open_cmd_and_check_system_configuration(db, with_cmd):
    agent, _ = make_agent(db, with_cmd, [
        s("open_app", "cmd"), s("run_command", "systeminfo"),
        s("finish", "Ran systeminfo in Command Prompt, bro.")])
    resp = agent.run("open cmd and check system configuration")
    assert with_cmd.launched == ["cmd.id"]
    assert with_cmd.foreground["hwnd"] == 70          # typed into cmd, nowhere else
    assert with_cmd.typed == ["systeminfo"] and with_cmd.keys_sent == [["enter"]]
    assert [st["action"] for st in resp["data"]["agent_steps"]] == ["open_app", "run_command"]
    assert resp["animation"] == "success"


def test_cmd_request_using_system_info_gets_nudged_to_run_command(db, with_cmd):
    agent, client = make_agent(db, with_cmd, [
        s("open_app", "cmd"), s("finish", "done"),       # opened cmd and stopped
        s("run_command", "systeminfo"), s("finish", "Done, bro.")])
    agent.run("open cmd and check system configuration")
    assert with_cmd.typed == ["systeminfo"]
    assert "command prompt" in client.calls[2][-1]["content"]


@pytest.mark.parametrize("command", ["del /s /q C:\\", "shutdown /s", "systeminfo & del x",
                                     "format c:", "powershell -enc AAAA", "rm -rf /"])
def test_run_command_refuses_anything_off_the_whitelist(with_cmd, command):
    with_cmd.windows.append({"hwnd": 70, "pid": 7, "process_name": "cmd.exe", "title": "cmd"})
    tools = AgentTools(with_cmd, sleep=lambda _s: None)
    ok, obs, _ = tools.run("run_command", command)
    assert not ok and "isn't allowed" in obs
    assert with_cmd.typed == [] and with_cmd.keys_sent == []


def test_run_command_only_types_into_a_terminal(os_adapter):
    os_adapter.foreground = {"hwnd": 50, "pid": 5, "process_name": "Notepad.exe",
                             "title": "Notepad"}
    os_adapter.windows = [os_adapter.foreground]
    ok, obs, _ = AgentTools(os_adapter, sleep=lambda _s: None).run("run_command", "systeminfo")
    assert not ok and "No Command Prompt is open" in obs and os_adapter.typed == []


def test_run_command_needs_the_user_to_ask_for_a_terminal():
    assert grounded("run_command", "systeminfo", "open cmd and check system configuration")
    assert grounded("run_command", "ipconfig", "run ipconfig for me")
    assert not grounded("run_command", "systeminfo", "open notepad and write hello")


def test_free_text_into_terminal_still_refused_with_hint(db, with_cmd):
    with_cmd.foreground = {"hwnd": 70, "pid": 7, "process_name": "cmd.exe", "title": "cmd"}
    with_cmd.windows = [with_cmd.foreground]
    ok, obs, _ = AgentTools(with_cmd, sleep=lambda _s: None).run("type_text", "dir")
    assert not ok and "run_command" in obs and with_cmd.typed == []


# ---- typing lands only in the target window -------------------------------

def test_typing_waits_for_the_window_and_targets_it(os_adapter):
    os_adapter.windows = [{"hwnd": 50, "pid": 5, "process_name": "Notepad.exe",
                           "title": "Notepad"}]
    tools = AgentTools(os_adapter, sleep=lambda _s: None)
    tools.active = os_adapter.windows[0]
    ok, obs, _ = tools.run("type_text", "how are you")
    assert ok and os_adapter.typed == ["how are you"]
    assert os_adapter.waited == [50]                 # waited for Notepad to be ready


def test_typing_stops_if_another_window_takes_focus(os_adapter):
    notepad = {"hwnd": 50, "pid": 5, "process_name": "Notepad.exe", "title": "Notepad"}
    os_adapter.windows = [notepad]
    os_adapter.wait_ready = lambda hwnd, timeout=2.0: True
    os_adapter.foreground = {"hwnd": 7, "pid": 7, "process_name": "chrome.exe", "title": "x"}
    os_adapter.focus_window = lambda hwnd: True      # claims success, focus never moves
    tools = AgentTools(os_adapter, sleep=lambda _s: None)
    tools.active = notepad
    ok, obs, _ = tools.run("type_text", "secret")
    assert not ok and "lost focus" in obs and os_adapter.typed == []


def test_no_typing_when_window_never_gets_ready(os_adapter):
    notepad = {"hwnd": 50, "pid": 5, "process_name": "Notepad.exe", "title": "Notepad"}
    os_adapter.windows = [notepad]
    os_adapter.wait_ready = lambda hwnd, timeout=2.0: False
    tools = AgentTools(os_adapter, sleep=lambda _s: None)
    tools.active = notepad
    ok, obs, _ = tools.run("type_text", "hi")
    assert not ok and "didn't type" in obs and os_adapter.typed == []


def test_open_app_waits_for_the_new_window_not_the_old_one(os_adapter):
    """Win 11 Notepad's new window appears ~1-2 s after launch; the old
    Notepad in front must not be taken meanwhile (typed into the old note)."""
    old = {"hwnd": 40, "pid": 4, "process_name": "Notepad.exe", "title": "old note - Notepad"}
    os_adapter.windows = [old]
    os_adapter.foreground = old
    now = [0.0]
    new = {"hwnd": 50, "pid": 5, "process_name": "Notepad.exe", "title": "Untitled - Notepad"}

    def sleep(secs):                      # the new window shows up after 1.5 s
        now[0] += secs
        if now[0] >= 1.5 and new not in os_adapter.windows:
            os_adapter.windows.append(new)

    os_adapter.launch_app = lambda app_id: os_adapter.launched.append(app_id) or True
    tools = AgentTools(os_adapter, sleep=sleep, clock=lambda: now[0])
    ok, _, _ = tools.run("open_app", "notepad")
    assert ok and tools.active["hwnd"] == 50
