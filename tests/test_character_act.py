"""The cat walks to a window's real button and presses it before Bro closes /
minimizes / maximizes it: the handshake, every hook, screen maths, drawing."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from backend.services.agent_service import AgentTools
from backend.services.character_service import CharacterActs
from backend.services.idle_app_service import IdleAppService
from backend.ws.notifications import NotificationManager
from client.walk_area import paw_window_target, physical_to_logical
from tests.fakes import FakeOSAdapter


class FakeNotifications:
    def __init__(self, deliver=True):
        self.sent: list[dict] = []
        self.deliver = deliver

    def broadcast_from_thread(self, payload):
        self.sent.append(payload)
        return self.deliver


class ButtonOS(FakeOSAdapter):
    def caption_button_point(self, hwnd, kind):
        return (900, 20) if kind in ("close", "minimize", "maximize", "close_tab") else None


class RecordingCharacter:
    """Stands in for CharacterActs; records order relative to the OS calls."""

    def __init__(self, os_adapter):
        self.os = os_adapter
        self.calls: list[tuple] = []

    def act(self, kind, hwnd, label=""):
        self.calls.append((kind, hwnd, len(self.os.closed), len(self.os.keys_sent)))
        return True


# ---- handshake --------------------------------------------------------------

def test_act_waits_for_the_paw_then_returns():
    notes = FakeNotifications()
    acts = CharacterActs(notes, ButtonOS(), timeout=2.0)
    threading.Timer(0.1, lambda: acts.done(notes.sent[0]["id"])).start()
    started = time.monotonic()
    assert acts.act("close", 5, "Notepad") is True
    assert time.monotonic() - started < 1.5
    event = notes.sent[0]
    assert (event["type"], event["kind"], event["x"], event["y"]) == ("character_act", "close", 900, 20)


def test_act_gives_up_fast_without_a_client_or_button():
    assert CharacterActs(FakeNotifications(deliver=False), ButtonOS()).act("close", 5) is False
    assert CharacterActs(FakeNotifications(), FakeOSAdapter()).act("close", 5) is False  # no point
    assert CharacterActs(FakeNotifications(), ButtonOS()).act("format_disk", 5) is False


def test_act_times_out_and_lets_the_action_happen():
    acts = CharacterActs(FakeNotifications(), ButtonOS(), timeout=0.1)
    assert acts.act("minimize", 5) is False
    assert acts.done("unknown-id") is False


def test_broadcast_from_a_worker_thread_reaches_the_loop():
    received = []

    class WS:
        async def send_json(self, payload):
            received.append(payload)

    async def main():
        manager = NotificationManager()
        manager.bind_loop(asyncio.get_running_loop())
        manager.connect(WS())
        sent = await asyncio.to_thread(manager.broadcast_from_thread, {"type": "character_act"})
        await asyncio.sleep(0.05)
        return sent

    assert asyncio.run(main()) is True and received == [{"type": "character_act"}]
    assert NotificationManager().broadcast_from_thread({"x": 1}) is False  # no loop/clients


# ---- hooks: the paw goes first, then the real action -------------------------

@pytest.fixture()
def notepad_os():
    fake = ButtonOS()
    win = {"hwnd": 50, "pid": 5, "process_name": "Notepad.exe", "title": "Notepad"}
    fake.windows, fake.foreground = [win], win
    return fake


def test_close_app_acts_before_closing(notepad_os):
    character = RecordingCharacter(notepad_os)
    tools = AgentTools(notepad_os, sleep=lambda _s: None, character=character)
    ok, _, _ = tools.run("close_app", "notepad")
    assert ok and character.calls == [("close", 50, 0, 0)] and notepad_os.closed == [50]


def test_minimize_and_maximize_act_before_the_keys(notepad_os):
    character = RecordingCharacter(notepad_os)
    tools = AgentTools(notepad_os, sleep=lambda _s: None, character=character)
    tools.active = notepad_os.windows[0]
    tools.run("windows_shortcut", "minimize_window")
    tools.run("windows_shortcut", "maximize_window")
    assert character.calls == [("minimize", 50, 0, 0), ("maximize", 50, 0, 1)]
    assert notepad_os.keys_sent == [["win", "down"], ["win", "up"]]


def test_close_tab_acts_and_other_shortcuts_dont(notepad_os):
    character = RecordingCharacter(notepad_os)
    tools = AgentTools(notepad_os, sleep=lambda _s: None, character=character)
    tools.active = notepad_os.windows[0]
    tools.run("app_action", "close_tab")
    tools.run("windows_shortcut", "volume_up")
    assert [c[0] for c in character.calls] == ["close_tab"]


def test_unused_app_yes_walks_to_its_x_then_closes():
    fake = ButtonOS()
    fake.windows = [{"hwnd": 70, "pid": 7, "process_name": "chrome.exe", "title": "Chrome"}]
    character = RecordingCharacter(fake)
    service = IdleAppService({"idleAppMinutes": 30}, fake, character=character)
    key = "proc:chrome"
    service._apps[key] = {"name": "Chrome", "last_active": 0.0}
    resp = service.answer(key, close=True)
    assert character.calls == [("close", 70, 0, 0)] and fake.closed == [70]
    assert "Closing Chrome" in resp["text"]


# ---- screen maths + drawing ------------------------------------------------

def test_physical_to_logical_at_125_percent():
    screens = [(0, 0, 1536, 864, 1.25)]
    assert physical_to_logical(1888, 9, screens) == pytest.approx((1510.4, 7.2))
    two = [(0, 0, 1536, 864, 1.25), (1536, 0, 1920, 1080, 1.0)]
    assert physical_to_logical(1536 + 1920 * 0.25 + 100, 50, two) == pytest.approx(
        (1536 + 580, 50))


def test_paw_lands_on_the_button():
    assert paw_window_target((1510, 7), (150, 26)) == (1360, -19)  # may poke above the top


def test_cat_draws_every_pose_and_reaches_with_its_paw():
    from client import cat_svg
    from client.animation import VALID_ANIMATIONS
    for pose in VALID_ANIMATIONS:
        svg = cat_svg.character_svg(pose, 3)
        assert svg.startswith("<svg") and "polygon" in svg  # ears = it's the cat
    press = cat_svg.character_svg("press")
    assert f'{cat_svg.PAW_TIP[0] - 6:.1f}' in press  # paw drawn at the touch point
    assert cat_svg.character_svg("reach") != cat_svg.character_svg("idle")


# ---- clear window commands skip the model -------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("minimize the window", ("windows_shortcut", "minimize_window", None)),
    ("bro minimise it", ("windows_shortcut", "minimize_window", None)),
    ("maximize notepad", ("windows_shortcut", "maximize_window", "notepad")),
    ("close it", ("close_app", "", None)),
    ("close this window", ("close_app", "", None)),
    ("close the tab", ("app_action", "close_tab", None)),
    ("close notepad", None),                 # the close_app rule handles it
    ("minimize all my worries please and thanks", None),
])
def test_window_command(text, expected):
    from backend.services.agent_service import window_command
    assert window_command(text) == expected


def test_minimize_the_window_needs_no_model_and_walks(notepad_os):
    from backend.services.agent_service import AgentService
    from tests.test_agent import CFG, ScriptedClient
    character = RecordingCharacter(notepad_os)
    client = ScriptedClient([])
    tools = AgentTools(notepad_os, sleep=lambda _s: None, character=character)
    agent = AgentService(None, CFG, notepad_os, client=client, tools=tools)
    resp = agent.run("minimize the window")
    assert client.calls == [] and notepad_os.keys_sent == [["win", "down"]]
    assert character.calls[0][0] == "minimize" and resp["text"].startswith("Done, bro")


def test_close_it_closes_the_app_we_worked_in(notepad_os):
    from backend.services.agent_service import AgentService
    from tests.test_agent import CFG, ScriptedClient
    character = RecordingCharacter(notepad_os)
    tools = AgentTools(notepad_os, sleep=lambda _s: None, character=character)
    tools.active = notepad_os.windows[0]
    agent = AgentService(None, CFG, notepad_os, client=ScriptedClient([]), tools=tools)
    session = agent.sessions.get_or_create(None)
    resp = agent.turn(session, "close it")
    assert notepad_os.closed == [50] and character.calls[0][:2] == ("close", 50)
    assert resp["data"]["status"] == "done"


def test_close_it_closes_only_that_window_not_the_whole_app():
    from backend.services.agent_service import AgentService
    from tests.test_agent import CFG, ScriptedClient
    fake = ButtonOS()
    mine = {"hwnd": 50, "pid": 5, "process_name": "Notepad.exe", "title": "Untitled - Notepad"}
    users_note = {"hwnd": 51, "pid": 5, "process_name": "Notepad.exe", "title": "*plans - Notepad"}
    fake.windows, fake.foreground = [mine, users_note], mine
    tools = AgentTools(fake, sleep=lambda _s: None, character=RecordingCharacter(fake))
    tools.active = mine
    agent = AgentService(None, CFG, fake, client=ScriptedClient([]), tools=tools)
    agent.turn(agent.sessions.get_or_create(None), "close it")
    assert fake.closed == [50]                       # the user's other note is untouched


def test_minimize_uses_the_real_button_action_when_available(notepad_os):
    """Live: Win+Down on a maximized Calculator only restored it."""
    states = []
    notepad_os.set_window_state = lambda hwnd, state: states.append((hwnd, state)) or True
    tools = AgentTools(notepad_os, sleep=lambda _s: None, character=RecordingCharacter(notepad_os))
    tools.active = notepad_os.windows[0]
    ok, _, _ = tools.run("windows_shortcut", "minimize_window")
    assert ok and states == [(50, "minimize")] and notepad_os.keys_sent == []
