"""Chat sessions: ask_user → answer → continue, follow-up work, /chat API,
and the client chat window (offscreen Qt). No Ollama, no real input."""

from __future__ import annotations

import os

import pytest

from backend.services import app_launcher_service
from backend.services.agent_service import AgentService, AgentTools, ChatSession, ChatSessions
from tests.fakes import FakeOSAdapter
from tests.test_agent import CFG, FakeSysInfo, ScriptedClient, s


@pytest.fixture(autouse=True)
def _clear_app_cache():
    app_launcher_service.clear_app_cache()
    yield
    app_launcher_service.clear_app_cache()


@pytest.fixture()
def os_adapter():
    fake = FakeOSAdapter()
    fake.apps = [{"name": "Notepad", "app_id": "notepad.id"}]
    orig = fake.launch_app

    def launch(app_id):
        fake.windows.append({"hwnd": 50, "pid": 5, "process_name": "Notepad.exe",
                             "title": "Untitled - Notepad"})
        return orig(app_id)

    fake.launch_app = launch
    return fake


def make(os_adapter, steps):
    client = ScriptedClient(steps)
    tools = AgentTools(os_adapter, sysinfo=FakeSysInfo(), sleep=lambda _s: None)
    agent = AgentService(None, CFG, os_adapter, client=client, tools=tools)
    return agent, client


def test_ask_user_then_continue_with_the_answer(os_adapter):
    agent, client = make(os_adapter, [
        s("ask_user", "What should I write, bro?"),
        s("open_app", "notepad"), s("type_text", "buy milk"), s("finish", "Done, bro.")])
    session = agent.sessions.get_or_create(None)

    first = agent.turn(session, "write a note in notepad")
    assert first["data"]["status"] == "question"
    assert first["text"] == "What should I write, bro?"
    assert os_adapter.typed == [] and session.awaiting_answer

    second = agent.turn(session, "buy milk")
    assert second["data"]["status"] == "done"
    assert os_adapter.typed == ["buy milk"]  # "buy milk" is grounded by the answer
    assert not session.awaiting_answer
    # the answer was passed to the model as an answer, not a new request
    assert {"role": "user", "content": "User's answer: buy milk"} in client.calls[1]


def test_follow_up_work_keeps_context(os_adapter):
    agent, client = make(os_adapter, [
        s("open_app", "notepad"), s("finish", "Opened it."),
        s("type_text", "hello again"), s("finish", "Typed it.")])
    session = agent.sessions.get_or_create(None)
    agent.turn(session, "open notepad")
    resp = agent.turn(session, "now type hello again")
    assert resp["text"] == "Typed it."
    assert os_adapter.typed == ["hello again"]
    # the 2nd request still sees the 1st exchange
    contents = [m["content"] for m in client.calls[-1]]
    assert "open notepad" in contents and "now type hello again" in contents


def test_one_shot_ask_cannot_use_ask_user(os_adapter):
    agent, _ = make(os_adapter, [s("ask_user", "what?")])
    assert agent.run("write something") is None  # rejected by parse_step


def test_sessions_expire_and_cap():
    now = [0.0]
    store = ChatSessions(lambda: AgentTools(None), clock=lambda: now[0], ttl=10,
                         max_sessions=2)
    a = store.get_or_create(None)
    assert store.get_or_create(a.id) is a
    now[0] = 20
    assert store.get_or_create(a.id) is not a  # expired -> fresh session
    b, c = store.get_or_create(None), store.get_or_create(None)
    assert len(store._sessions) == 2 and c.id in store._sessions
    assert store.end(c.id) and not store.end(c.id)


def test_history_is_trimmed_to_recent_turns():
    session = ChatSession(id="x", tools=AgentTools(None))
    base = session._base_len
    for i in range(60):
        session.add_exchange(f"question {i}", f"answer {i}")
    convo = session.messages[base:]
    assert len(convo) <= 40 and convo[0]["role"] == "user"
    assert convo[-1]["content"].endswith('"answer 59"}')


# ---- /chat API ------------------------------------------------------------

@pytest.fixture()
def chat_client(client, os_adapter):
    agent, script = make(os_adapter, [])
    client.app.state.agent = agent
    return client, script


def test_chat_endpoint_question_then_answer(chat_client, os_adapter):
    client, script = chat_client
    script.steps = [s("ask_user", "Which text, bro?"),
                    s("open_app", "notepad"), s("type_text", "hi"), s("finish", "Done!")]
    r1 = client.post("/chat", json={"text": "write a note in notepad"}).json()
    assert r1["status"] == "question" and r1["session_id"]
    r2 = client.post("/chat", json={"text": "hi", "session_id": r1["session_id"]}).json()
    assert r2["status"] == "done" and r2["text"] == "Done!"
    assert [st["action"] for st in r2["steps"]] == ["open_app", "type_text"]
    assert os_adapter.typed == ["hi"]


def test_chat_simple_question_uses_rules_not_agent(chat_client):
    client, script = chat_client
    r = client.post("/chat", json={"text": "how much water did I drink today"}).json()
    assert r["status"] == "done" and "water" in r["text"].lower()
    assert script.calls == []  # instant path, no model call


def test_chat_not_understood(chat_client):
    client, script = chat_client
    script.steps = [None]
    r = client.post("/chat", json={"text": "asdfghjkl"}).json()
    assert r["animation"] == "confused" and "say it another way" in r["text"]


def test_chat_needs_ai(client):
    assert client.post("/chat", json={"text": "hi"}).status_code == 503


def test_end_chat(chat_client):
    client, script = chat_client
    script.steps = [s("finish", "Hey bro!")]
    sid = client.post("/chat", json={"text": "hello there"}).json()["session_id"]
    assert client.delete(f"/chat/{sid}").json() == {"ended": True}


# ---- client window (offscreen) -------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PyQt6.QtWidgets")
    return widgets.QApplication.instance() or widgets.QApplication([])


class FakeApi:
    def __init__(self):
        self.calls = []

    def call(self, method, path, on_done=None, on_error=None, **kwargs):
        self.calls.append((method, path, kwargs, on_done, on_error))


def test_chat_window_flow(qapp):
    from client.chat_window import PLACEHOLDER_ANSWER, PLACEHOLDER_MORE, ChatWindow, steps_summary

    api = FakeApi()
    win = ChatWindow(api)
    win._input.setText("write a note")
    win.send()
    method, path, kwargs, on_done, _ = api.calls[-1]
    assert (method, path) == ("post", "/chat") and kwargs["json"]["session_id"] is None
    assert win.busy and not win._send_btn.isEnabled()

    on_done({"session_id": "abc", "text": "What should I write?", "animation": "thinking",
             "status": "question", "steps": []})
    assert win.session_id == "abc" and not win.busy
    assert win._input.placeholderText() == PLACEHOLDER_ANSWER

    win._input.setText("buy milk")
    win.send()
    assert api.calls[-1][2]["json"] == {"text": "buy milk", "session_id": "abc"}
    api.calls[-1][3]({"session_id": "abc", "text": "Done", "animation": "success",
                      "status": "done", "steps": [{"action": "type_text", "ok": True,
                                                   "observation": "Typed it."}]})
    assert win._input.placeholderText() == PLACEHOLDER_MORE

    win.new_chat()
    assert win.session_id is None and api.calls[-1][:2] == ("delete", "/chat/abc")
    assert steps_summary([{"ok": False, "observation": "nope"}]) == "✗ nope"


def test_chat_emote_is_instant_with_motion(chat_client):
    client, script = chat_client
    r = client.post("/chat", json={"text": "dance again bro"}).json()
    assert r["animation"] == "dance" and r["motion"] is None
    r = client.post("/chat", json={"text": "go left", "session_id": r["session_id"]}).json()
    assert r["animation"] == "walk" and r["motion"] == "left"
    assert script.calls == []


def test_chat_agent_reply_gets_mood(chat_client):
    client, script = chat_client
    script.steps = [s("finish", "Why did the droplet blush? It saw the sea weed!")]
    r = client.post("/chat", json={"text": "tell me a joke"}).json()
    assert r["animation"] == "laugh"


def test_chat_small_talk_goes_to_agent_not_intent_parser(chat_client):
    client, script = chat_client
    script.steps = [s("finish", "You're welcome, bro!")]
    r = client.post("/chat", json={"text": "thank you bro"}).json()
    assert r["text"] == "You're welcome, bro!" and r["animation"] == "happy"


# ---- context memory: follow-ups, SQLite store, delete on close ------------

def _own_window():
    return {"hwnd": 99, "pid": os.getpid(), "process_name": "python.exe",
            "title": "Chat with Bro"}


def test_open_then_write_types_into_the_opened_app(chat_client, os_adapter):
    """The user's example: 'bro open the notepad' then 'write how are you'."""
    client, script = chat_client
    r1 = client.post("/chat", json={"text": "bro open the notepad"}).json()
    assert r1["animation"] == "success" and "Notepad" in r1["text"]
    assert script.calls == []                        # instant rules path, no model
    os_adapter.foreground = _own_window()            # user typed in Bro's chat box
    script.steps = [s("type_text", "how are you"), s("finish", "Wrote it, bro.")]
    r2 = client.post("/chat", json={"text": "write how are you",
                                    "session_id": r1["session_id"]}).json()
    assert os_adapter.typed == ["how are you"]
    assert os_adapter.foreground["hwnd"] == 50       # into Notepad, not the chat
    # both turns are in the chat's history (context for later messages)
    session = client.app.state.agent.sessions._sessions[r1["session_id"]]
    history = " ".join(m["content"] for m in session.conversation())
    assert "bro open the notepad" in history and '"open_app"' in history
    assert "write how are you" in history and '"type_text"' in history


def test_never_types_into_bros_own_window(os_adapter):
    os_adapter.foreground = _own_window()
    os_adapter.windows = [os_adapter.foreground]
    ok, obs, _ = AgentTools(os_adapter, sleep=lambda _s: None).run("type_text", "hi")
    assert not ok and "No app is open" in obs and os_adapter.typed == []


@pytest.fixture()
def stored_chat(chat_client):
    from backend.db.repositories.chat_repo import ChatRepo
    client, script = chat_client
    agent = client.app.state.agent
    agent.sessions.repo = ChatRepo(client.app.state.db)
    return client, script, agent, agent.sessions.repo


def test_chat_context_is_saved_in_sqlite_and_deleted_on_close(stored_chat):
    client, script, agent, repo = stored_chat
    r = client.post("/chat", json={"text": "open notepad"}).json()
    stored = repo.load(r["session_id"])
    assert stored["user_texts"] == ["open notepad"]
    assert stored["active_window"]["hwnd"] == 50
    assert any("open notepad" in m["content"] for m in stored["messages"])

    assert client.delete(f"/chat/{r['session_id']}").json() == {"ended": True}
    assert repo.load(r["session_id"]) is None and repo.count() == 0


def test_chat_context_survives_a_backend_restart(stored_chat, os_adapter):
    client, script, agent, repo = stored_chat
    r1 = client.post("/chat", json={"text": "open notepad"}).json()
    agent.sessions._sessions.clear()                 # memory lost (restart)
    agent._tools.active = None
    script.steps = [s("type_text", "how are you"), s("finish", "Done, bro.")]
    r2 = client.post("/chat", json={"text": "write how are you",
                                    "session_id": r1["session_id"]}).json()
    assert r2["session_id"] == r1["session_id"]
    assert os_adapter.typed == ["how are you"] and os_adapter.foreground["hwnd"] == 50
    restored = agent.sessions._sessions[r1["session_id"]]
    assert "open notepad" in " ".join(m["content"] for m in restored.conversation())


def test_idle_chats_are_purged_from_sqlite(db_repo_clock):
    sessions, repo, wall = db_repo_clock
    old = sessions.get_or_create(None)
    sessions.save(old)
    wall[0] += 31 * 60                               # 31 min idle
    sessions.clock = lambda: wall[0]
    sessions.get_or_create(None)                     # any access purges
    assert repo.load(old.id) is None


@pytest.fixture()
def db_repo_clock(os_adapter):
    from backend.db.connection import Database
    from backend.db.migrations import migrate
    from backend.db.repositories.chat_repo import ChatRepo
    database = Database(":memory:")
    migrate(database.raw)
    wall = [1_000_000.0]
    repo = ChatRepo(database)
    sessions = ChatSessions(lambda: AgentTools(os_adapter, sleep=lambda _s: None),
                            clock=lambda: wall[0], repo=repo, wall=lambda: wall[0])
    yield sessions, repo, wall
    database.close()


def test_closing_the_chat_window_deletes_the_context(qapp):
    from client.chat_window import ChatWindow
    api = FakeApi()
    win = ChatWindow(api)
    win._input.setText("open notepad")
    win.send()
    api.calls[-1][3]({"session_id": "abc", "text": "Opened Notepad.", "animation": "success",
                      "status": "done", "steps": []})
    win.close()
    assert [c[:2] for c in api.calls[-2:]] == [("delete", "/chat/abc"),
                                              ("post", "/ai/unload")]  # RAM freed too
    assert win.session_id is None
    # a reply still on its way after close is dropped and its chat deleted too
    win._input.setText("write hi")
    win.send()
    pending_reply = api.calls[-1][3]
    win.close()
    pending_reply({"session_id": "def", "text": "late", "animation": "success",
                      "status": "done", "steps": []})
    assert win.session_id is None and api.calls[-1][:2] == ("delete", "/chat/def")


def test_chat_says_when_ollama_is_down(chat_client):
    client, script = chat_client
    script.steps = [None]                       # model call failed
    script.ping = lambda: False                 # ...because Ollama isn't running
    r = client.post("/chat", json={"text": "write a note in notepad"}).json()
    assert "Ollama" in r["text"] and "isn't running" in r["text"]
    assert r["animation"] == "confused"


# ---- "write X [in APP]": exact text, no model -------------------------------

@pytest.mark.parametrize("text, expected", [
    ("write how are you", ("how are you", None)),
    ("write how are you in the notepad", ("how are you", "notepad")),
    ("bro can you type 'i love you' into notepad", ("i love you", "notepad")),
    ("Write: Meet me at 5 in notepad.", ("Meet me at 5", "notepad")),
    ("write meet me in the morning", ("meet me", "morning")),   # app checked later
    ("write a note in notepad", None),         # compose -> the agent asks
    ("write it in notepad", None),
    ("open notepad and write hello", None),    # multi-step -> the agent
])
def test_parse_write_request(text, expected):
    from backend.services.agent_service import parse_write_request
    got = parse_write_request(text)
    assert (got[:2] if got else None) == expected


def test_write_in_notepad_types_exact_text_without_the_model(chat_client, os_adapter):
    client, script = chat_client
    os_adapter.foreground = _own_window()
    r = client.post("/chat", json={"text": "write how are you in the notepad"}).json()
    assert os_adapter.typed == ["how are you"] and os_adapter.foreground["hwnd"] == 50
    assert r["status"] == "done" and r["animation"] == "success"
    assert [st["action"] for st in r["steps"]] == ["open_app", "type_text"]
    assert script.calls == []                          # no model: nothing to misread


def test_open_then_write_reuses_the_opened_app(chat_client, os_adapter):
    client, script = chat_client
    r1 = client.post("/chat", json={"text": "bro open the notepad"}).json()
    os_adapter.foreground = _own_window()
    r2 = client.post("/chat", json={"text": "write how are you",
                                    "session_id": r1["session_id"]}).json()
    assert os_adapter.launched == ["notepad.id"]       # not opened twice
    assert os_adapter.typed == ["how are you"] and "Notepad" in r2["text"]
    assert script.calls == []


def test_write_without_an_app_asks_which_then_types(chat_client, os_adapter):
    client, script = chat_client
    os_adapter.foreground = _own_window()
    r1 = client.post("/chat", json={"text": "write how are you"}).json()
    assert r1["status"] == "question" and "Which app" in r1["text"]
    assert os_adapter.typed == []
    r2 = client.post("/chat", json={"text": "in notepad",
                                    "session_id": r1["session_id"]}).json()
    assert os_adapter.typed == ["how are you"] and r2["status"] == "done"


def test_write_with_non_app_words_keeps_them_in_the_text(chat_client, os_adapter):
    client, script = chat_client
    client.post("/chat", json={"text": "open notepad"})
    sid = client.app.state.agent.sessions._sessions
    session_id = next(iter(sid))
    client.post("/chat", json={"text": "write meet me in the morning", "session_id": session_id})
    assert os_adapter.typed == ["meet me in the morning"]
