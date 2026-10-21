"""Multi-agent system: ai/llm.py is the only LLM file, the main agent assigns
the right sub-agent, sub-agents stay inside their own tools, answers go back
to whoever asked, a crash in one agent doesn't break the chat, and the
instant routes never call the model (no lag)."""

from __future__ import annotations

import pathlib
import threading
import time

import pytest

from ai.agent_prompts import build_agent_messages
from ai.llm import LLM
from backend.agents.base import AgentContext, AgentReply, SubAgent
from backend.agents.main_agent import AGENT_FAILED, MainAgent
from backend.agents.writer_agent import WriterAgent
from backend.services.agent_service import AgentService, AgentTools, parse_step
from tests.fakes import FakeOSAdapter
from tests.test_agent import CFG, FakeSysInfo, ScriptedClient, s

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---- ai/llm.py is the only file that talks to the model provider -------------

def test_only_llm_py_talks_to_the_provider():
    offenders = []
    for path in [*ROOT.glob("ai/*.py"), *ROOT.glob("backend/**/*.py"), *ROOT.glob("client/*.py")]:
        if path.name in ("llm.py", "ollama_client.py"):
            continue
        source = path.read_text(encoding="utf-8")
        if "/api/chat" in source or "/api/tags" in source or "OllamaClient(" in source:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_llm_choose_ping_and_warm_up_never_raise():
    def post(url, json=None, timeout=None):
        assert json["format"]["properties"]["choice"]["enum"] == ["a", "b"]
        return FakeResponse({"message": {"content": '{"choice": "b"}'}})

    assert LLM(CFG, post=post).choose("which?", ["a", "b"]) == "b"
    bad = LLM(CFG, post=lambda *a, **k: FakeResponse({"message": {"content": '{"choice":"x"}'}}))
    assert bad.choose("which?", ["a", "b"]) is None          # off-list answer rejected

    def down(*a, **k):
        raise ConnectionError("no provider")
    assert LLM(CFG, post=down, get=down).ping() is False
    assert LLM(CFG, post=down).chat([{"role": "user", "content": "hi"}]) is None
    LLM(CFG, post=down).warm_up(["m1"])                      # just doesn't raise
    assert LLM(CFG, get=lambda *a, **k: FakeResponse({}, 200)).ping() is True


# ---- routing -------------------------------------------------------------------

class CountingLLM:
    """Scripted steps + counts every model call (routing must not add lag)."""

    def __init__(self, steps=(), pick=None):
        self.steps, self.pick, self.chat_calls, self.choose_calls = list(steps), pick, 0, 0

    def chat(self, messages, **kwargs):
        self.chat_calls += 1
        self.last_schema = kwargs.get("schema")
        self.last_messages = messages
        if not self.steps:
            return None
        import json
        return {"message": {"content": json.dumps(self.steps.pop(0))}}

    def choose(self, question, options):
        self.choose_calls += 1
        return self.pick

    def ping(self):
        return True


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


def make_main(os_adapter, llm):
    tools = AgentTools(os_adapter, sysinfo=FakeSysInfo(), sleep=lambda _s: None)
    engine = AgentService(None, CFG, os_adapter, client=llm, tools=tools)
    return MainAgent(AgentContext(config=CFG, engine=engine, os_adapter=os_adapter)), engine


@pytest.mark.parametrize("text, agent", [
    ("tell me a joke", "companion"),
    ("I'm so bored today", "companion"),
    ("take a screenshot", "system"),
    ("how much RAM does my pc have", "system"),
    ("open cmd and check system configuration", "system"),
    ("open a new tab", "writer"),
    ("open notepad and write hi", "writer"),
    ("make it bold", "writer"),
    ("hey open chrome and go to youtube.com", "window"),
    ("open notepad, write hi, then check my battery", "general"),
])
def test_main_agent_routes_by_domain_without_a_model_call(os_adapter, text, agent):
    llm = CountingLLM()
    main, _ = make_main(os_adapter, llm)
    assert main.route(text, None) == agent
    assert llm.chat_calls == 0 and llm.choose_calls == 0   # instant routing


def test_unclear_requests_ask_the_model_which_agent(os_adapter):
    llm = CountingLLM(pick="companion")
    main, _ = make_main(os_adapter, llm)
    assert main.route("asdf qwerty", None) == "companion" and llm.choose_calls == 1
    llm.pick = None                                          # model unsure / down
    assert main.route("asdf qwerty", None) == "general"


# ---- isolation: each sub-agent thinks with its own prompt and tools ----------

def test_sub_agent_prompt_has_only_its_tools():
    writer = WriterAgent.spec
    prompt = build_agent_messages(chat=True, tools=set(writer.tools), role=writer.role)
    system = prompt[0]["content"]
    assert "- type_text:" in system and "- run_command:" not in system
    assert "- system_info:" not in system and "Your job: work inside apps" in system
    full = build_agent_messages(chat=True)
    assert sum(len(m["content"]) for m in prompt) < sum(len(m["content"]) for m in full)


def test_sub_agent_cannot_use_another_agents_tool():
    response = {"message": {"content": '{"thought": "t", "action": "run_command", "input": "ver"}'}}
    assert parse_step(response, chat=True, tools=set(WriterAgent.spec.tools)) is None
    assert parse_step(response, chat=True, tools=None) is not None   # general may


def test_writer_loop_gets_writer_schema_and_prompt(os_adapter):
    llm = CountingLLM(steps=[s("ask_user", "What should I write, bro?")])
    main, engine = make_main(os_adapter, llm)
    session = engine.sessions.get_or_create(None)
    reply = main.handle(session, "write a note in notepad")
    assert reply.agent == "writer" and reply.status == "question"
    assert "run_command" not in llm.last_schema["properties"]["action"]["enum"]
    assert "Your job: work inside apps" in llm.last_messages[0]["content"]


def test_answer_goes_back_to_the_agent_that_asked(os_adapter):
    llm = CountingLLM(steps=[s("ask_user", "What should I write?"),
                             s("open_app", "notepad"), s("type_text", "buy milk"),
                             s("finish", "Done, bro.")])
    main, engine = make_main(os_adapter, llm)
    session = engine.sessions.get_or_create(None)
    main.handle(session, "write a note in notepad")
    reply = main.handle(session, "buy milk")               # would look like small talk
    assert reply.agent == "writer" and os_adapter.typed == ["buy milk"]


def test_switching_agents_keeps_the_shared_conversation(os_adapter):
    llm = CountingLLM(steps=[s("finish", "Ha! A joke, bro.")])
    main, engine = make_main(os_adapter, llm)
    session = engine.sessions.get_or_create(None)
    main.handle(session, "open notepad")                   # window agent (instant)
    main.handle(session, "tell me a joke")                 # companion agent (model)
    history = " ".join(m["content"] for m in session.conversation())
    assert "open notepad" in history and "tell me a joke" in history
    assert session.prompt_owner == "companion"


def test_a_crashing_sub_agent_does_not_break_the_chat(os_adapter):
    main, engine = make_main(os_adapter, CountingLLM())

    class Broken(SubAgent):
        spec = WriterAgent.spec

        def claim(self, session, text, ctx):
            raise RuntimeError("boom")

    main.agents["writer"] = Broken()
    session = engine.sessions.get_or_create(None)
    reply = main.handle(session, "write hi in notepad")
    assert reply.text == AGENT_FAILED
    assert main.handle(session, "dance").agent == "companion"   # still works after


# ---- instant routes never call the model (no lag) -----------------------------

@pytest.mark.parametrize("text, agent", [
    ("dance", "companion"), ("open notepad", "window"),
    ("write hello in notepad", "writer"), ("minimize the window", "window"),
])
def test_instant_routes_make_no_model_call(os_adapter, text, agent):
    llm = CountingLLM()
    main, engine = make_main(os_adapter, llm)
    session = engine.sessions.get_or_create(None)
    if text == "minimize the window":
        main.handle(session, "open notepad")
    reply = main.handle(session, text)
    assert reply.agent == agent and llm.chat_calls == 0 and llm.choose_calls == 0


def test_chat_api_reports_which_agent_answered(client, os_adapter):
    llm = CountingLLM()
    tools = AgentTools(os_adapter, sysinfo=FakeSysInfo(), sleep=lambda _s: None)
    client.app.state.agent = AgentService(None, CFG, os_adapter, client=llm, tools=tools)
    assert client.post("/chat", json={"text": "how much water did I drink today"}).json()["agent"] == "stats"
    assert client.post("/chat", json={"text": "dance"}).json()["agent"] == "companion"
    assert client.post("/chat", json={"text": "open notepad"}).json()["agent"] == "window"


def test_same_chat_can_not_run_two_messages_at_once(client, os_adapter):
    """A second message while the first is still working gets 409, so two
    agents never act on the same chat at the same time."""
    release = threading.Event()

    class SlowLLM(CountingLLM):
        def chat(self, messages, **kwargs):
            release.wait(2)
            return None

    tools = AgentTools(os_adapter, sysinfo=FakeSysInfo(), sleep=lambda _s: None)
    client.app.state.agent = AgentService(None, CFG, os_adapter, client=SlowLLM(), tools=tools)
    sid = client.post("/chat", json={"text": "dance"}).json()["session_id"]
    first = threading.Thread(target=lambda: client.post(
        "/chat", json={"text": "tell me a joke", "session_id": sid}))
    first.start()
    time.sleep(0.2)
    second = client.post("/chat", json={"text": "dance", "session_id": sid})
    release.set()
    first.join()
    assert second.status_code == 409


# ---- no model reloads: one context size per model ----------------------------

def test_every_call_to_a_model_uses_the_same_context_size():
    """Live: a different num_ctx made Ollama reload the model (2.8 s -> 8.3 s)."""
    seen = []

    def post(url, json=None, timeout=None):
        seen.append((json["model"], json.get("options", {}).get("num_ctx")))
        return FakeResponse({"message": {"content": '{"choice": "a"}'}})

    cfg = {**CFG, "ai": {**CFG["ai"], "model": "small", "agent": {"model": "big"}}}
    llm = LLM(cfg, post=post)
    llm.warm_up()
    llm.chat([], model="big", num_ctx=6144)       # agent loop
    llm.choose("which?", ["a"])                     # main agent's pick (agent model)
    llm.chat([], num_ctx=2048)                      # intent gateway (small model)
    sizes = {}
    for model, ctx in seen:
        sizes.setdefault(model, set()).add(ctx)
    assert sizes == {"small": {1024}, "big": {6144}}


def test_log_rotation_survives_a_locked_file(tmp_path, monkeypatch):
    import logging
    from backend.logging_setup import SafeRotatingFileHandler
    handler = SafeRotatingFileHandler(tmp_path / "a.log", maxBytes=50, backupCount=2,
                                      encoding="utf-8")
    monkeypatch.setattr("os.rename", lambda *a: (_ for _ in ()).throw(PermissionError("locked")))
    monkeypatch.setattr("os.replace", lambda *a: (_ for _ in ()).throw(PermissionError("locked")))
    logger = logging.getLogger("rotation-test")
    logger.addHandler(handler)
    logger.propagate = False
    for i in range(20):
        logger.warning("line %d with some padding to pass maxBytes", i)  # no exception
    handler.close()
    assert "line 19" in (tmp_path / "a.log").read_text(encoding="utf-8")


# ---- common requests are instant inside their sub-agent ---------------------

@pytest.mark.parametrize("text, topic", [
    ("how much RAM does my pc have", "memory"), ("check my battery", "battery"),
    ("what cpu is in my laptop", "cpu"), ("show my system configuration", "all"),
])
def test_pc_questions_read_the_right_part_without_the_model(os_adapter, text, topic):
    llm = CountingLLM()
    main, engine = make_main(os_adapter, llm)
    reply = main.handle(engine.sessions.get_or_create(None), text)
    assert reply.agent == "system" and reply.steps[0]["input"] == topic
    assert llm.chat_calls == 0 and "Here you go" in reply.text


@pytest.mark.parametrize("text", ["open battery settings", "open cmd and check my battery"])
def test_pc_requests_that_need_more_are_not_grabbed_by_the_instant_rule(os_adapter, text):
    from backend.agents.system_agent import SystemAgent
    main, engine = make_main(os_adapter, CountingLLM())
    session = engine.sessions.get_or_create(None)
    assert SystemAgent().claim(session, text, main.ctx) is None  # not a plain PC question
    assert main.route(text, None) == "system"                    # but still the system agent's


@pytest.mark.parametrize("text, action, keys", [
    ("open a new tab", "new_tab", ["ctrl", "t"]), ("make it bold", None, None),
    ("undo that", "undo", ["ctrl", "z"]), ("find my files", None, None),
])
def test_direct_app_actions_in_the_app_in_front(os_adapter, text, action, keys):
    chrome = {"hwnd": 60, "pid": 6, "process_name": "chrome.exe", "title": "Chrome"}
    os_adapter.windows, os_adapter.foreground = [chrome], chrome
    llm = CountingLLM(steps=[s("finish", "thinking it over")])
    main, engine = make_main(os_adapter, llm)
    session = engine.sessions.get_or_create(None)
    reply = main.handle(session, text)
    if action:
        assert reply.agent == "writer" and os_adapter.keys_sent == [keys] and llm.chat_calls == 0
    else:  # chrome has no "bold"; "find my files" is too vague: no keys pressed by rule
        assert os_adapter.keys_sent == []


# ---- one model, and its RAM is freed when not in use --------------------------

def test_one_model_for_everything_by_default():
    from backend.config import load_config
    llm = LLM(load_config(user_path=pathlib.Path("does-not-exist.json")))
    assert llm.default_model() == llm.agent_model() == "qwen2.5:1.5b"


def test_unload_frees_the_model_and_never_raises():
    seen = []
    LLM(CFG, post=lambda url, json=None, timeout=None: seen.append(json)).unload()
    assert seen and all(p["keep_alive"] == 0 for p in seen)
    def down(*a, **k):
        raise ConnectionError("no provider")
    LLM(CFG, post=down).unload()  # doesn't raise


def test_warm_and_unload_endpoints_return_at_once(cfg, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from ai import llm as llm_module
    calls = []
    monkeypatch.setattr(llm_module.LLM, "warm_up", lambda self, models=None: calls.append("warm"))
    monkeypatch.setattr(llm_module.LLM, "unload", lambda self, models=None: calls.append("unload"))
    cfg = {**cfg, "ai": {**cfg["ai"], "enabled": True}}
    app = create_app(cfg, start_services=False)
    with TestClient(app) as c:
        headers = {"X-Arun-Token": app.state.api_token}
        assert c.post("/ai/warm", headers=headers).json() == {"ok": True}
        assert c.post("/ai/unload", headers=headers).json() == {"ok": True}
        time.sleep(0.2)
    assert sorted(calls) == ["unload", "warm"]


def test_no_model_is_loaded_at_startup(cfg, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from ai import llm as llm_module
    warmed = []
    monkeypatch.setattr(llm_module.LLM, "warm_up", lambda self, models=None: warmed.append(1))
    monkeypatch.setattr(llm_module.LLM, "unload", lambda self, models=None: None)
    cfg = {**cfg, "ai": {**cfg["ai"], "enabled": True}}
    with TestClient(create_app(cfg, start_services=True)):
        time.sleep(0.2)
    assert warmed == []   # RAM stays free until the chat opens
