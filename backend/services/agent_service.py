"""Agent loop: think -> act -> observe, repeated until the job is done.

The model (ai/agent_prompts.py) picks ONE whitelisted tool per step; this
module validates the step, runs it through AgentTools, feeds the result back
as an Observation and asks again — until the model calls `finish`, the step
budget runs out, or it starts repeating itself. Ollama only chooses; the
backend decides what actually runs (golden rule). There is no free shell
tool: keys are whitelisted, credential prompts are never typed into, and a
terminal only ever receives one of a few fixed read-only commands
(SAFE_TERMINAL_COMMANDS, e.g. `systeminfo`) via run_command.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher, get_close_matches
from typing import Any, Callable

from ai.agent_prompts import (AGENT_TOOLS, CHAT_TOOLS, allowed_tools,
                              build_agent_messages, observation_message, step_schema)
from ai.tool_catalog import (APP_ACTIONS, SEND_ON_ENTER_APPS, WINDOWS_SHORTCUTS,
                             actions_for, app_for_process)
from ai.llm import get_llm
from backend.db.repositories.ai_repo import AiRepo
from backend.db.repositories.chat_repo import ChatRepo
from backend.os_integration.helpers import app_identity, process_label
from backend.services.app_launcher_service import _DOMAIN, AppLauncherService, _score
from backend.services.character_service import act_then
from backend.services.system_info_service import SystemInfoService
from backend.services.system_service import SystemService

logger = logging.getLogger("arun.agent")

MAX_TASK_CHARS = 300
MAX_INPUT_CHARS = 500
DEFAULT_MAX_STEPS = 8
DEFAULT_TIMEOUT_SECONDS = 60
MAX_HISTORY_MESSAGES = 40  # chat turns kept after prompt + examples
SESSION_TTL_SECONDS = 30 * 60
WINDOW_WAIT_SECONDS = 8.0
REUSE_GRACE_SECONDS = 3.0  # wait this long for a NEW window before reusing one

# never type or press keys into these: a typed line + Enter would run as a
# command, and credential prompts are the user's alone
BLOCKED_PROCESSES = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "wt.exe",
    "conhost.exe", "openconsole.exe", "wsl.exe", "bash.exe", "mintty.exe",
    "consent.exe", "credentialuibroker.exe", "logonui.exe", "regedit.exe",
    "mmc.exe", "taskmgr.exe",
}

TERMINAL_PROCESSES = {"cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe",
                      "wt.exe", "conhost.exe", "openconsole.exe"}
# the ONLY lines run_command may type into a terminal: fixed, read-only, no
# arguments from the model (a typed line + Enter runs as a command)
SAFE_TERMINAL_COMMANDS = ("systeminfo", "ipconfig", "ipconfig /all", "tasklist",
                          "hostname", "whoami", "ver")
_TERMINAL = re.compile(r"\b(?:cmd|command prompt|command line|terminal|powershell|console)\b")

# shortcuts/actions the cat acts out by pressing the window's real button
PAW_BUTTONS = {"minimize_window": "minimize", "maximize_window": "maximize",
               "close_tab": "close_tab"}

# one successful step of these finishes a one-part request (see the loop)
ONE_SHOT_TOOLS = {"windows_shortcut", "app_action"}

SEND_REFUSAL = ("I don't press Enter in a messaging app — that would send the message "
                "for you. It's typed; you press Enter to send.")


def _catalog_key(name: str) -> str:
    """'Show Desktop' / 'new-tab' -> 'show_desktop' / 'new_tab'."""
    return re.sub(r"[\s\-]+", "_", name.lower().strip().strip("`'\"")).strip("_")


SAFE_KEYS = {"enter", "tab", "escape", "backspace", "delete", "space", "up",
             "down", "left", "right", "home", "end", "pageup", "pagedown"}
SAFE_COMBOS = {("ctrl", k) for k in "acvxzysnfwt"} | {("ctrl", "shift", "s"),
                                                      ("shift", "tab")}
KEY_ALIASES = {"esc": "escape", "return": "enter", "control": "ctrl",
               "del": "delete", "spacebar": "space", "pgup": "pageup",
               "pgdn": "pagedown"}

# -- which requests need the agent (vs. one rule/intent) -------------------
_VERB = (r"(?:open|launch|start|close|quit|write|type|press|save|search|go to|"
         r"check|show|find|play|create|make|copy|paste|enter|select|tell)")
_MULTI_STEP = re.compile(rf"\b{_VERB}\b.+?(?:\band then\b|\bthen\b|\band\b|,)\s*"
                         rf"(?:\w+\s+){{0,2}}{_VERB}\b")
_TYPING = re.compile(r"\b(?:write|type|draft|jot down|note down)\b")
_DEVICE = r"(?:system|pc|computer|laptop|machine|device)"
_SPEC = r"(?:config\w*|spec\w*|info\w*|details?|hardware|status|health)"
_HW = r"(?:ram|memory|cpu|processor|gpu|graphics card|battery|disk space|storage)"
_SYSINFO = re.compile(rf"\b{_DEVICE}\b.*\b{_SPEC}\b|\b{_SPEC}\b.*\b{_DEVICE}\b|"
                      rf"\b(?:how much|what|which|check)\b.*\b{_HW}\b")


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9,+' ]+", " ", text.lower()).split())


# Windows features / in-app actions the tool catalog covers ("take a
# screenshot", "new tab", "make it bold"): the agent's shortcut tools do these
_FEATURE = re.compile(
    r"\b(?:screenshot|screen shot|snip|show (?:the )?desktop|minimi[sz]e|maximi[sz]e|"
    r"snap|task view|virtual desktop|new desktop|next desktop|previous desktop|"
    r"clipboard|emoji|magnif\w*|notifications?|quick settings|widgets?|voice typing|"
    r"dictat\w*|game bar|captions?|volume|mute|unmute|next (?:song|track)|"
    r"previous (?:song|track)|play|pause|new tab|close (?:the |this )?tab|reopen|"
    r"next tab|previous tab|refresh|reload|go back|go forward|bold|italic|underline|"
    r"align\w*|bullet|zoom|new folder|rename|full screen|scroll|slideshow|new slide|"
    r"autosum|incognito|private window|bookmark|switch window)\b")
# ("downloads" is left out: "tidy my downloads" is the Downloads folder)


def needs_agent(text: str) -> bool:
    """True for multi-step jobs, typing, questions about this PC, and
    Windows / in-app features (shortcut tools) — a single rule/intent would
    do only part of them (e.g. open Notepad but never type, or open Settings
    instead of reading the specs)."""
    t = _norm(text)
    return bool(_MULTI_STEP.search(t) or _TYPING.search(t) or _SYSINFO.search(t)
                or _FEATURE.search(t))


_WINDOW_CMD = re.compile(
    r"^(?:(?:please|pls|bro|hey|can you|could you|just|now)[\s,]+)*"
    r"(?P<verb>minimi[sz]e|maximi[sz]e|close)\s+(?P<what>.+?)\s*[.!]?$", re.I)
_THIS = r"(?:the\s+|this\s+|that\s+|my\s+|current\s+)?"
_IT = re.compile(rf"^(?:it|this|that|{_THIS}(?:window|app))$", re.I)
_TAB = re.compile(rf"^{_THIS}tab$", re.I)


def window_command(text: str) -> tuple[str, str, str | None] | None:
    """(tool, input, app or None) for "minimize the window", "maximize
    notepad", "close it", "close this tab"; None otherwise. "close notepad"
    is left to the existing close_app rule (it also walks to the X)."""
    m = _WINDOW_CMD.match(text.strip())
    if not m:
        return None
    verb, what = m.group("verb").lower(), m.group("what").strip()
    if verb == "close":
        if _TAB.match(what):
            return "app_action", "close_tab", None
        return ("close_app", "", None) if _IT.match(what) else None
    shortcut = "minimize_window" if verb.startswith("minimi") else "maximize_window"
    if _IT.match(what):
        return "windows_shortcut", shortcut, None
    app = re.sub(rf"^{_THIS}", "", re.sub(r"\s+window$", "", what), flags=re.I).strip()
    return ("windows_shortcut", shortcut, app) if app and len(app.split()) <= 3 else None


def _mentions(task: str, name: str, words: tuple[str, ...], description: str) -> bool:
    """Did the user ask for this shortcut/action? Its trigger words, all of
    its name's words, or two words of its description must be in the request
    (stops the model copying the prompt's examples for unrelated text)."""
    t = _norm(task)
    if any(w in t for w in words):
        return True
    t_words = set(t.split())
    name_words = [w for w in name.split("_") if w]
    if name_words and all(w in t_words for w in name_words):
        return True
    desc_words = {w for w in _norm(description).split() if len(w) > 3}
    return len(desc_words & t_words) >= 2 or any(
        len(w) >= 4 and w in t_words for w in name_words)


def _action_description(name: str) -> str:
    """Description of an app action in any app (for grounding)."""
    key = _catalog_key(name)
    for app in [None, *APP_ACTIONS]:
        action = actions_for(app).get(key)
        if action:
            return action[1]
    return ""


# "write how are you", "type 'hi' in notepad": the text is the user's own
# words, so code types it exactly — the small model tends to ask "what
# should I write?" (copying its few-shot example) or rephrase the text
_WRITE_REQ = re.compile(
    r"^\s*(?:(?:hey|bro|please|pls|can you|could you|will you|now|just|also)[\s,]+)*"
    r"(?:write|type)(?:\s+(?:down|out))?\s*:?\s+(?P<body>.+?)\s*[.!]?\s*$", re.I | re.S)
_IN_APP = re.compile(r"^(?P<text>.+?)\s+(?:in|into|on)\s+(?:(?:the|a|my|new)\s+)*"
                     r"(?P<app>[\w.+-]+(?:\s+[\w.+-]+){0,2}?)(?:\s+(?:app|window))?\s*$",
                     re.I | re.S)
# "write a note / an email / something" = compose it: that's the agent's job
_COMPOSE = re.compile(r"^(?:(?:a|an|some|the|my)\s+(?:note|message|mail|email|letter|"
                      r"story|poem|essay|paragraph|list|reply)\b|something\b|"
                      r"(?:it|this|that)$)", re.I)
_QUOTES = "\"'“”‘’`"


def parse_write_request(text: str) -> tuple[str, str | None, str] | None:
    """('how are you', 'notepad' | None, full body) for a plain "write X
    [in APP]" request; None for multi-step jobs or "write a note…" (the
    agent composes / asks those). `app` is only a candidate: the caller
    checks it's a real app, else the whole body is the text."""
    if _MULTI_STEP.search(_norm(text)):
        return None
    m = _WRITE_REQ.match(text)
    if not m:
        return None
    full = m.group("body").strip().strip(_QUOTES).strip()
    body, app = full, None
    im = _IN_APP.match(full)
    if im:
        body, app = im.group("text").strip().strip(_QUOTES).strip(), im.group("app")
    if not body or _COMPOSE.match(body):
        return None
    return body, app, full


_FILLER = {"a", "an", "the", "my", "app", "application", "window", "for", "me",
           "please", "to", "in", "on", "of", "and", "settings", "setting", "page",
           "www", "com", "https", "http"}
# tools whose input must come from the user's own words (small models
# otherwise copy the prompt's examples: "asdf" -> open notepad, type hello)
GROUNDED_TOOLS = {"open_app", "close_app", "focus_window", "type_text", "open_website"}


def _command_key(command: str) -> str:
    return " ".join(command.lower().strip().strip("`'\"").split())


def grounded(action: str, arg: str, task: str) -> bool:
    """Is this step's target actually in the request? type_text may write
    new content only when the user asked for writing."""
    if action == "system_info":  # read-only, but only when the user asked
        return bool(_SYSINFO.search(_norm(task)) or re.search(
            rf"\b(?:{_HW}|{_DEVICE}|specs?|os|windows)\b", _norm(task)))
    if action == "run_command":  # only when the user asked for a terminal
        first = (_command_key(arg).split() or [""])[0]
        t = _norm(task)
        return bool(_TERMINAL.search(t) or (first and first in t.split()))
    if action == "windows_shortcut":
        entry = WINDOWS_SHORTCUTS.get(_catalog_key(arg))
        if entry is None:
            return True  # unknown name: the tool explains and lists close ones
        return _mentions(task, _catalog_key(arg), entry[2], entry[1])
    if action == "app_action":
        return _mentions(task, _catalog_key(arg), (), _action_description(arg))
    if action not in GROUNDED_TOOLS:
        return True
    if action == "type_text" and _TYPING.search(_norm(task)):
        return True
    t_words = _norm(task).replace(",", " ").split()
    words = [w for w in _norm(arg).replace(",", " ").split() if w not in _FILLER]
    if not words:
        return False
    if "".join(words) in "".join(t_words):  # "vs code" ~ "vscode"
        return True
    hits = sum(1 for w in words
               if w in t_words or any(SequenceMatcher(None, w, tw).ratio() >= 0.8
                                      for tw in t_words))
    return hits / len(words) >= 0.6


def _required_tools(text: str) -> dict[str, str]:
    """Tools the request obviously needs -> nudge if the model skips them."""
    t = _norm(text)
    req = {}
    if _TYPING.search(t):
        req["type_text"] = "The request asks to write/type text, but nothing was typed yet."
    if _SYSINFO.search(t) and _TERMINAL.search(t):
        req["run_command"] = ("The user asked to use the command prompt: run "
                              "run_command systeminfo there.")
    elif _SYSINFO.search(t):
        req["system_info"] = "The request is about this PC, but system_info was not used yet."
    return req


# -- the hands --------------------------------------------------------------
class AgentTools:
    """Executes one validated step. Returns (ok, observation, report) where
    `report` is data worth showing the user verbatim (specs, window list)."""

    def __init__(self, os_adapter, sysinfo: SystemInfoService | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 character: Any | None = None):
        self.os = os_adapter
        self.character = character  # walks to a button and presses it first
        self.sysinfo = sysinfo or SystemInfoService()
        self.sleep = sleep
        self.clock = clock
        self.active: dict[str, Any] | None = None  # window we're working in
        self.own_pid = os.getpid()

    def run(self, action: str, arg: str) -> tuple[bool, str, str | None]:
        handler = getattr(self, f"_t_{action}", None)
        if handler is None:
            return False, f"Unknown tool '{action}'.", None
        try:
            return handler(arg.strip())
        except Exception as exc:  # a tool bug must not kill the loop
            logger.exception("agent tool %s failed", action)
            return False, f"{action} failed: {exc}", None

    # ---- window helpers ----
    def _windows(self) -> list[dict[str, Any]]:
        return self.os.list_windows() if self.os is not None else []

    @staticmethod
    def _name(win: dict[str, Any]) -> str:
        key, name = app_identity(win)
        return name if key.startswith("title:") else process_label(win.get("process_name"))

    def _match_score(self, query: str, win: dict[str, Any]) -> float:
        score = _score(query, self._name(win))
        title = _score(query, win.get("title") or "")
        return max(score, title if title >= 70 else 0.0)

    def _find_window(self, query: str) -> dict[str, Any] | None:
        best = max(((self._match_score(query, w), w) for w in self._windows()),
                   key=lambda p: p[0], default=(0.0, None))
        return best[1] if best[0] > 0 else None

    def _wait_for_window(self, name: str, before: set[int]) -> dict[str, Any] | None:
        """A freshly launched app's window — or, for single-window apps that
        reuse a running instance (Win 11 Notepad adds a tab), the matching
        window that came to the front."""
        start = self.clock()
        deadline = start + WINDOW_WAIT_SECONDS
        while True:
            matches = [w for w in self._windows() if self._match_score(name, w) > 0]
            fresh = [w for w in matches if w["hwnd"] not in before]
            if fresh:
                return fresh[0]
            # an already-open window only counts once a new one had time to
            # appear: Notepad's new window can take ~1-2 s, and grabbing the
            # old one typed into the previous note
            fg = self.os.get_foreground_window()
            if (self.clock() - start >= REUSE_GRACE_SECONDS and fg
                    and any(w["hwnd"] == fg.get("hwnd") for w in matches)):
                return fg
            if self.clock() >= deadline:
                return matches[0] if matches else None
            self.sleep(0.25)

    def _alive(self, win: dict[str, Any] | None) -> dict[str, Any] | None:
        if win is None:
            return None
        return next((w for w in self._windows() if w["hwnd"] == win["hwnd"]), None)

    @staticmethod
    def _blocked(win: dict[str, Any] | None) -> bool:
        return bool(win) and (win.get("process_name") or "").lower() in BLOCKED_PROCESSES

    def _input_target(self) -> tuple[dict[str, Any] | None, str | None]:
        """(window to type into, error). Active window first, else foreground."""
        if self.os is None:
            return None, "Typing isn't available on this system."
        target = self._alive(self.active) or self.os.get_foreground_window()
        if target and self._own(target):
            # the user just typed in Bro's chat box, so it's in front — that
            # is never where "write X" should go
            target = None
        if not target:
            return None, ("No app is open to type into. Open one first with open_app "
                          "(or use ask_user to ask which app).")
        if self._blocked(target):
            hint = (" For a read-only command like systeminfo, use run_command."
                    if self._is_terminal(target) else " Ask the user to do that part.")
            return None, (f"I won't type free text into {self._name(target)} — it's a "
                          f"terminal or system prompt.{hint}")
        error = self._bring_front(target)
        return (None, error) if error else (target, None)

    def _own(self, win: dict[str, Any]) -> bool:
        """One of Bro's own windows (chat, bubble): backend and client share
        a process when started with run.py."""
        return win.get("pid") == self.own_pid

    @staticmethod
    def _is_terminal(win: dict[str, Any] | None) -> bool:
        return bool(win) and (win.get("process_name") or "").lower() in TERMINAL_PROCESSES

    def _terminal_target(self) -> tuple[dict[str, Any] | None, str | None]:
        """The open terminal to run a command in: active, front, else any."""
        if self.os is None:
            return None, "Commands aren't available on this system."
        candidates = [self._alive(self.active), self.os.get_foreground_window()]
        candidates += self._windows()
        target = next((w for w in candidates if self._is_terminal(w)), None)
        if target is None:
            return None, "No Command Prompt is open. Open it first with open_app cmd."
        error = self._bring_front(target)
        return (None, error) if error else (target, None)

    def _bring_front(self, target: dict[str, Any]) -> str | None:
        fg = self.os.get_foreground_window()
        if not fg or fg.get("hwnd") != target["hwnd"]:
            if not self.os.focus_window(target["hwnd"]):
                self.sleep(0.3)  # a just-opened window may still be settling
                if not self.os.focus_window(target["hwnd"]):
                    return f"Couldn't bring {self._name(target)} to the front."
        # keys sent while Windows is still switching windows are dropped
        if not self.os.wait_ready(target["hwnd"]):
            return f"{self._name(target)} didn't come to the front, so I didn't type."
        return None

    # ---- tools ----
    def _t_open_app(self, name: str):
        if not name:
            return False, "open_app needs an app name.", None
        before = {w["hwnd"] for w in self._windows()}
        res = AppLauncherService(self.os).open_app(name)
        if res["status"] == "opened_url":
            return True, f"Opened {res['name']} in the browser.", None
        if res["status"] == "not_found":
            return False, f"No app called '{name}' is installed on this PC.", None
        if res["status"] != "opened":
            return False, f"Windows wouldn't start {res['name'] or name}.", None
        win = self._wait_for_window(res["name"], before)
        if win is None:
            return True, (f"Started {res['name']}, but its window hasn't appeared yet. "
                          "Use wait, then try again."), None
        self.active = win
        self.os.focus_window(win["hwnd"])
        self.sleep(0.4)  # let the app finish drawing before keys arrive
        return True, f"Opened {res['name']}. It is in front now.", None

    def _t_focus_window(self, name: str):
        win = self._find_window(name)
        if win is None:
            return False, f"{name} isn't open. Use open_app first.", None
        self.active = win
        if not self.os.focus_window(win["hwnd"]):
            return False, f"Couldn't bring {self._name(win)} to the front.", None
        return True, f"{self._name(win)} is in front now.", None

    def _t_close_app(self, name: str):
        res = AppLauncherService(self.os).close_app(name, character=self.character)
        if res["status"] == "closed":
            if self.active and not self._alive(self.active):
                self.active = None
            return True, f"Closed {res['name']} (it may ask to save first).", None
        if res["status"] == "not_running":
            return False, f"{name} isn't running.", None
        return False, f"Couldn't close {res['name'] or name}.", None

    def close_one(self, win: dict[str, Any]) -> tuple[bool, str]:
        """Close just this window (the cat walks to its X first)."""
        name = self._name(win)
        act_then(self.character, "close", win["hwnd"], name)
        if not self.os.close_window(win["hwnd"]):
            return False, f"Couldn't close {name}."
        if self.active and self.active.get("hwnd") == win["hwnd"]:
            self.active = None
        return True, f"Closed {name} (it may ask to save first)."

    def _t_type_text(self, text: str):
        if not text:
            return False, "type_text needs the text to type.", None
        target, error = self._input_target()
        if error:
            return False, error, None
        text = text.replace("\\n", "\n")
        if "\n" in text and self._sends_on_enter(target):
            text = text.replace("\n", " ")  # a newline would send the message
        if not self.os.type_text(text, hwnd=target["hwnd"]):
            return False, (f"Typing stopped: {self._name(target)} lost focus (another "
                           "window came to the front), so the text may be incomplete."), None
        self.active = target
        return True, f"Typed '{text}' into {self._name(target)}.", None

    def _t_run_command(self, command: str):
        key = _command_key(command)
        if key not in SAFE_TERMINAL_COMMANDS:
            return False, (f"'{command}' isn't allowed. I can only run these read-only "
                           f"commands: {', '.join(SAFE_TERMINAL_COMMANDS)}."), None
        target, error = self._terminal_target()
        if error:
            return False, error, None
        if not self.os.type_text(key, hwnd=target["hwnd"]) or not self.os.send_keys(["enter"]):
            return False, f"Couldn't run {key}.", None
        self.active = target
        self.sleep(0.5)
        return True, (f"Ran '{key}' in {self._name(target)}. Its output is showing "
                      "there now."), None

    def _t_press_key(self, combo: str):
        keys = [KEY_ALIASES.get(k, k) for k in
                re.split(r"\s*\+\s*", combo.lower().strip()) if k]
        allowed = (len(keys) == 1 and keys[0] in SAFE_KEYS) or tuple(keys) in SAFE_COMBOS
        if not allowed:
            return False, f"'{combo}' isn't a key I'm allowed to press.", None
        target, error = self._input_target()
        if error:
            return False, error, None
        if "enter" in keys and self._sends_on_enter(target):
            return False, SEND_REFUSAL, None
        if not self.os.send_keys(keys):
            return False, f"Couldn't press {combo}.", None
        self.sleep(0.3)
        return True, f"Pressed {'+'.join(keys)} in {self._name(target)}.", None

    # ---- catalog tools: Windows shortcuts, observe an app, act in it ----
    @staticmethod
    def _sends_on_enter(win: dict[str, Any] | None) -> bool:
        return app_for_process((win or {}).get("process_name")) in SEND_ON_ENTER_APPS

    def _app_target(self) -> dict[str, Any] | None:
        """The app we're working in (never Bro's own window)."""
        if self.os is None:
            return None
        target = self._alive(self.active) or self.os.get_foreground_window()
        return None if (not target or self._own(target)) else target

    def _t_windows_shortcut(self, name: str):
        key = _catalog_key(name)
        entry = WINDOWS_SHORTCUTS.get(key)
        if entry is None:
            close = get_close_matches(key, list(WINDOWS_SHORTCUTS), n=3, cutoff=0.5)
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            return False, f"'{name}' isn't one of the Windows shortcuts.{hint}", None
        keys, what, _words, scope = entry
        where = ""
        if scope == "window":  # snap / maximize act on the app we work in
            target, error = self._input_target()
            if error:
                return False, error, None
            where = f" ({self._name(target)})"
            if key in PAW_BUTTONS:  # the cat walks over and presses the button
                act_then(self.character, PAW_BUTTONS[key], target["hwnd"], self._name(target))
                if self.os.set_window_state(target["hwnd"], PAW_BUTTONS[key]):
                    self.sleep(0.3)  # = the real button; Win+Down only restores maximized
                    return True, f"{what}{where}.", None
        if not self.os.send_keys(keys):
            return False, f"Couldn't press {'+'.join(keys)}.", None
        self.sleep(0.5)
        return True, f"{what}{where}.", None

    def _t_app_actions(self, _arg: str):
        """OBSERVE: what can the app in front do, and how is it used?"""
        target = self._app_target()
        if target is None:
            return False, "No app is in front. Open one first with open_app.", None
        app_key = app_for_process(target.get("process_name"))
        listing = "; ".join(f"{n} = {d}" for n, (_k, d) in actions_for(app_key).items())
        how = APP_ACTIONS[app_key]["how"] if app_key else "Common actions work in most apps."
        label = f"{self._name(target)} ({app_key})" if app_key else self._name(target)
        return True, f"{label} actions: {listing}. How to use: {how}", None

    def _t_app_action(self, name: str):
        target, error = self._input_target()
        if error:
            return False, error, None
        app_key = app_for_process(target.get("process_name"))
        actions = actions_for(app_key)
        key = _catalog_key(name)
        if key not in actions:
            close = get_close_matches(key, list(actions), n=3, cutoff=0.5)
            hint = f" Maybe: {', '.join(close)}." if close else ""
            return False, (f"{self._name(target)} has no action '{name}'. Use app_actions "
                           f"to see what it can do.{hint}"), None
        keys, what = actions[key]
        if "enter" in keys and app_key in SEND_ON_ENTER_APPS:
            return False, SEND_REFUSAL, None
        if key in PAW_BUTTONS:
            act_then(self.character, PAW_BUTTONS[key], target["hwnd"], self._name(target))
        if not self.os.send_keys(keys):
            return False, f"Couldn't do {key} in {self._name(target)}.", None
        self.sleep(0.4)
        return True, f"{what} in {self._name(target)}.", None

    def _t_open_settings(self, page: str):
        res = SystemService(self.os).open_settings(page)
        if res["status"] != "opened":
            return False, "Couldn't open Settings.", None
        return True, f"Opened the {res['page']} Settings page.", None

    def _t_open_website(self, address: str):
        address = address.strip()
        if not (_DOMAIN.match(address) or address.startswith(("http://", "https://"))):
            return False, f"'{address}' doesn't look like a web address.", None
        ok = AppLauncherService(self.os).open_site(address)
        return (True, f"Opened {address} in the browser.", None) if ok else \
               (False, f"Couldn't open {address}.", None)

    def _t_system_info(self, what: str):
        report = self.sysinfo.report(what or "all")
        return True, report, report

    def _t_list_windows(self, _arg: str):
        names = sorted({self._name(w) for w in self._windows()})
        report = "Open apps: " + (", ".join(names) or "none")
        return True, report, report

    def _t_wait(self, seconds: str):
        try:
            secs = min(5.0, max(1.0, float(re.findall(r"[\d.]+", seconds)[0])))
        except (IndexError, ValueError):
            secs = 2.0
        self.sleep(secs)
        return True, f"Waited {secs:g} seconds.", None


# -- the loop ---------------------------------------------------------------
def parse_step(response: Any, chat: bool = False,
               tools: set[str] | None = None) -> dict[str, str] | None:
    """Model response -> {thought, action, input} or None (validated).
    `tools` = the running sub-agent's whitelist: anything else is rejected
    even if the model names it (an agent can't use another agent's tools)."""
    try:
        step = json.loads(response["message"]["content"])
    except (TypeError, KeyError, ValueError):
        return None
    allowed = allowed_tools(chat, tools)
    if not isinstance(step, dict) or step.get("action") not in allowed:
        return None
    arg = step.get("input", "")
    if not isinstance(arg, str):
        arg = "" if arg is None else str(arg)
    thought = step.get("thought") if isinstance(step.get("thought"), str) else ""
    return {"thought": thought[:300], "action": step["action"],
            "input": arg[:MAX_INPUT_CHARS]}


@dataclass
class ChatSession:
    """One conversation: the model's message history, the window the agent
    is working in, and whether it's waiting for the user's answer.
    chat=False is a one-shot /ask run (no ask_user, thrown away after)."""
    id: str
    tools: AgentTools
    chat: bool = True
    messages: list[dict[str, str]] = field(default_factory=list)
    user_texts: list[str] = field(default_factory=list)  # grounding source
    request: str = ""          # current request + its clarifications
    awaiting_answer: bool = False
    pending_write: str | None = None  # "write X" waiting for "which app?"
    last_agent: str | None = None     # sub-agent that handled the last message
    prompt_owner: str = "general"     # whose system prompt `messages` starts with
    last_used: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if not self.messages:
            self.messages = build_agent_messages(chat=self.chat)
        self._base_len = len(self.messages)

    def add_user(self, text: str) -> None:
        """Route a user message: answer to our question, or a new request."""
        if self.awaiting_answer:
            self.messages.append({"role": "user", "content": f"User's answer: {text}"})
            self.request = f"{self.request} {text}".strip()
            self.awaiting_answer = False
        else:
            self.messages.append({"role": "user", "content": text})
            self.request = text
        self.user_texts.append(text)
        self._trim()

    def add_exchange(self, text: str, reply: str) -> None:
        """A message answered outside the agent (rules / stats): keep it in
        the history so later messages can refer to it."""
        self.add_user(text)
        self.messages.append({"role": "assistant", "content": json.dumps(
            {"thought": "Answered from Arun's own data.", "action": "finish",
             "input": reply})})

    def add_tool_exchange(self, text: str, steps: list[tuple[str, str, str]],
                          reply: str) -> None:
        """A quick command (rules, no model call) run with this session's own
        tools: record its (action, input, observation) steps as real steps
        so follow-ups ("write hi", "close it") know what was opened."""
        self.add_user(text)
        for action, arg, observation in steps:
            self.messages.append({"role": "assistant", "content": json.dumps(
                {"thought": "Quick command.", "action": action, "input": arg})})
            self.messages.append(observation_message(observation))
        self.messages.append({"role": "assistant", "content": json.dumps(
            {"thought": "Done.", "action": "finish", "input": reply})})

    def conversation(self) -> list[dict[str, str]]:
        """This chat's messages after the fixed prompt + examples."""
        return self.messages[self._base_len:]

    def use_prompt(self, base: list[dict[str, str]], owner: str) -> None:
        """Switch to another sub-agent's prompt + examples; the conversation
        (shared by all sub-agents of this chat) stays as it is."""
        convo = self.conversation()
        self.messages = list(base) + convo
        self._base_len = len(base)
        self.prompt_owner = owner

    def add_reply(self, reply: str) -> None:
        """Close a turn that produced no model reply (so history stays paired)."""
        self.messages.append({"role": "assistant", "content": json.dumps(
            {"thought": "I didn't understand.", "action": "finish", "input": reply})})

    def grounding_text(self) -> str:
        return " ".join(self.user_texts)

    def _trim(self) -> None:
        """Keep the prompt + examples and the latest turns (num_ctx is 4096)."""
        convo = self.messages[self._base_len:]
        if len(convo) > MAX_HISTORY_MESSAGES:
            convo = convo[-MAX_HISTORY_MESSAGES:]
            while convo and convo[0]["role"] != "user":  # start on a user turn
                convo = convo[1:]
            self.messages = self.messages[:self._base_len] + convo


class ChatSessions:
    """The chat window's conversations (single user, a few sessions): kept in
    memory and mirrored to SQLite (ChatRepo) while the chat is open, so the
    context survives a backend restart; deleted when the chat is closed or
    idle for `ttl` seconds."""

    def __init__(self, factory: Callable[[], AgentTools], clock=time.monotonic,
                 ttl: float = SESSION_TTL_SECONDS, max_sessions: int = 5,
                 repo: ChatRepo | None = None, wall: Callable[[], float] = time.time):
        self.factory = factory
        self.clock = clock
        self.ttl = ttl
        self.max_sessions = max_sessions
        self.repo = repo
        self.wall = wall
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str | None) -> ChatSession:
        with self._lock:
            now = self.clock()
            for sid in [k for k, v in self._sessions.items() if now - v.last_used > self.ttl]:
                self._drop(sid)
            self._repo_call("purge_older_than", self.wall() - self.ttl)
            session = self._sessions.get(session_id or "")
            if session is None and session_id:
                session = self._restore(session_id)
            if session is None:
                session = ChatSession(id=uuid.uuid4().hex, tools=self.factory())
            if session.id not in self._sessions:
                while len(self._sessions) >= self.max_sessions:
                    oldest = min(self._sessions.values(), key=lambda v: v.last_used)
                    self._drop(oldest.id)
                self._sessions[session.id] = session
            session.last_used = now
            return session

    def save(self, session: ChatSession) -> None:
        """Persist after each turn — unless the chat was closed meanwhile."""
        if session.id not in self._sessions:
            return
        self._repo_call("save", session.id, now=self.wall(), request=session.request,
                        awaiting_answer=session.awaiting_answer,
                        user_texts=session.user_texts,
                        active_window=session.tools.active,
                        messages=session.conversation())

    def end(self, session_id: str) -> bool:
        """The user closed the chat: forget its context everywhere."""
        with self._lock:
            known = session_id in self._sessions
            self._drop(session_id)
            return known

    def _drop(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._repo_call("delete", session_id)

    def _restore(self, session_id: str) -> ChatSession | None:
        stored = self._repo_call("load", session_id)
        if not stored:
            return None
        session = ChatSession(id=stored["id"], tools=self.factory())
        session.messages.extend(stored["messages"])
        session.request = stored["request"]
        session.awaiting_answer = stored["awaiting_answer"]
        session.user_texts = list(stored["user_texts"])
        session.tools.active = stored["active_window"]  # re-checked before use
        return session

    def _repo_call(self, method: str, *args, **kwargs):
        if self.repo is None:
            return None
        try:
            return getattr(self.repo, method)(*args, **kwargs)
        except Exception:  # memory still works if the DB hiccups
            logger.exception("chat store %s failed", method)
            return None


class AgentService:
    def __init__(self, db, config: dict[str, Any], os_adapter=None,
                 client: Any | None = None, tools: AgentTools | None = None,
                 character: Any | None = None):
        self.db = db
        self.config = config
        self.os = os_adapter
        self.character = character
        self.client = client if client is not None else get_llm(config)
        self._tools = tools
        self.sessions = ChatSessions(self._new_tools,
                                     repo=ChatRepo(db) if db is not None else None)

    def _new_tools(self) -> AgentTools:
        return self._tools or AgentTools(self.os, character=self.character)

    @property
    def settings(self) -> dict[str, Any]:
        return self.config.get("ai", {}).get("agent", {})

    @property
    def enabled(self) -> bool:
        ai = self.config.get("ai", {})
        return bool(ai.get("enabled")) and self.settings.get("enabled", True)

    def run(self, text: str, spec: Any | None = None) -> dict[str, Any] | None:
        """One-shot (POST /ask). Envelope dict, or None if the model couldn't
        be reached / nothing was achieved (router falls back to clarification)."""
        if not self.enabled:
            return None
        session = ChatSession(id="oneshot", tools=self._new_tools(), chat=False)
        return self.turn(session, text, spec)

    def turn(self, session: ChatSession, text: str,
             spec: Any | None = None) -> dict[str, Any] | None:
        """Feed one user message into a session and loop until the model
        finishes, asks the user something (chat only) or gets stuck.
        `spec` = the sub-agent doing the work (backend/agents): its role
        and tool whitelist; None = the general agent with every tool."""
        if not self.enabled:
            return None
        task = text.strip()[:MAX_TASK_CHARS]
        quick = None if session.awaiting_answer else self._window_job(session, task)
        if quick is not None:
            return quick
        agent_tools = set(spec.tools) if spec is not None else None
        owner = spec.name if spec is not None else "general"
        if session.prompt_owner != owner:  # another sub-agent's prompt is loaded
            session.use_prompt(build_agent_messages(
                chat=session.chat, tools=agent_tools,
                role=spec.role if spec is not None else None), owner)
        session.add_user(task)
        max_steps = int(self.settings.get("maxSteps", DEFAULT_MAX_STEPS))
        model = self.settings.get("model") or None
        # a bigger agent model can need ~40 s to load cold; warm steps are ~4 s
        timeout = float(self.settings.get("timeoutSeconds", DEFAULT_TIMEOUT_SECONDS))
        messages = session.messages
        tools = session.tools
        grounding = session.grounding_text()
        required = {name: hint for name, hint in _required_tools(session.request).items()
                    if agent_tools is None or name in agent_tools}
        steps: list[dict[str, Any]] = []
        reports: list[str] = []
        final: str | None = None
        question: str | None = None
        nudged: set[str] = set()
        started = time.monotonic()
        failed_model = False

        for _ in range(max_steps):
            step = parse_step(self.client.chat(messages,
                                               schema=step_schema(session.chat, agent_tools),
                                               # the full tool catalog makes the prompt ~2.3k
                                               # tokens; a sub-agent's own prompt is smaller
                                               model=model, num_predict=200, num_ctx=6144,
                                               timeout=timeout),
                              chat=session.chat, tools=agent_tools)
            if step is None:
                failed_model = True
                break
            messages.append({"role": "assistant", "content": json.dumps(step)})
            logger.info("agent step: %s(%r) — %s", step["action"], step["input"], step["thought"])

            if step["action"] == "ask_user":
                question = step["input"].strip() or "Can you tell me a bit more, bro?"
                session.awaiting_answer = True
                break

            if step["action"] == "finish":
                done_tools = {s["action"] for s in steps if s["ok"]}
                missing = [t for t in required if t not in done_tools and t not in nudged]
                if missing:  # model claimed success without doing the work
                    nudged.update(missing)
                    messages.append(observation_message(
                        " ".join(required[t] for t in missing) + " Do it now."))
                    continue
                final = step["input"].strip()
                break

            key = (step["action"], step["input"].lower())
            if any(s["ok"] and (s["action"], s["input"].lower()) == key for s in steps):
                repeats = sum(1 for s in steps if s.get("repeat"))
                if repeats >= 1:
                    break  # stuck in a loop
                steps.append({**step, "ok": True, "repeat": True,
                              "observation": "already done"})
                messages.append(observation_message(
                    "You already did exactly that and it worked. Do the NEXT part "
                    "of the request, or finish if everything is done."))
                continue

            refused = not grounded(step["action"], step["input"], grounding)
            if step["action"] == "wait" and not any(
                    s["ok"] and s["action"] in ("open_app", "open_website") for s in steps):
                refused = True  # nothing is loading: waiting is a stall, not a step
                ok, observation, report = False, (
                    "Nothing is loading, so there is nothing to wait for. Do the request "
                    "or answer with finish."), None
            elif (step["action"] == "open_settings" and _SYSINFO.search(_norm(session.request))
                  and "setting" not in session.request.lower()):
                refused = True  # "check my battery" means read it, not open a page
                ok, observation, report = False, (
                    "The user wants to KNOW this, not open Settings. Use system_info "
                    "to read it."), None
            elif step["action"] == "system_info" and refused:
                ok, observation, report = False, (
                    "That is not a question about this PC, so system_info can't help. "
                    "No tool is needed: answer the user yourself with finish."), None
            elif refused:
                hint = " If you need a detail, use ask_user." if session.chat else ""
                ok, observation, report = False, (
                    f"'{step['input']}' is not in the user's request, so I did NOT do "
                    "that. Only do what the request says, using the user's own words; "
                    f"if nothing fits, use finish.{hint}"), None
            else:
                ok, observation, report = tools.run(step["action"], step["input"])
            if report:
                reports.append(report)
            steps.append({**step, "ok": ok, "observation": observation,
                          "refused": refused})
            messages.append(observation_message(observation))
            if (ok and step["action"] in ONE_SHOT_TOOLS
                    and not _MULTI_STEP.search(_norm(session.request))):
                # "volume up", "take a screenshot": one action IS the job. The
                # small model kept pressing more keys (then said it was stuck)
                # and copied the example's reply, so the backend ends it here
                final = f"Done, bro — {observation}"
                messages.append({"role": "assistant", "content": json.dumps(
                    {"thought": "Done.", "action": "finish", "input": final})})
                break
            if len(steps) >= 3 and not any(s["ok"] for s in steps[-3:]):
                break  # three failures in a row: it's not getting anywhere

        result = self._reply(final, steps, reports, question)
        self._log(task, steps, started, success=final is not None or question is not None)
        if result is not None and result["data"]["status"] == "stuck":
            # close the turn in the history so the next message starts fresh
            messages.append({"role": "assistant", "content": json.dumps(
                {"thought": "I got stuck.", "action": "finish", "input": result["text"]})})
        if result is None and failed_model and not steps:
            return None
        return result

    # ---- "minimize the window", "close it", "close this tab": no model ----
    def _window_job(self, session: ChatSession, task: str) -> dict[str, Any] | None:
        """Clear window commands run straight away (the cat walks to the
        button): live, the small model answered "minimize the window" with
        Esc and then claimed it had minimized."""
        parsed = window_command(task)
        if parsed is None:
            return None
        action, arg, app_name = parsed
        tools = session.tools
        if app_name:  # "minimize notepad": that app's window becomes the target
            win = tools._find_window(app_name)
            if win is None:
                return None  # not an open app: let the normal path handle it
            tools.active = win
        elif action != "close_app" and tools._app_target() is None:
            return None
        if action == "close_app":
            target = tools._alive(tools.active) or tools._app_target()
            if target is None:
                return None
            # "close it" = THIS window, not every window of the app (that
            # would also hit the user's other, unsaved Notepad notes)
            arg = tools._name(target)
            ok, observation = tools.close_one(target)
        else:
            ok, observation, _ = tools.run(action, arg)
        reply = f"Done, bro — {observation}" if ok else observation
        session.add_tool_exchange(task, [(action, arg, observation)], reply)
        return {"text": reply, "animation": "success" if ok else "warn",
                "needs_confirmation": False, "proposal_id": None,
                "data": {"status": "done", "agent_steps": [
                    {"action": action, "input": arg, "ok": ok, "observation": observation}]}}

    # ---- reply ----
    @staticmethod
    def _reply(final: str | None, steps: list[dict[str, Any]],
               reports: list[str], question: str | None = None) -> dict[str, Any] | None:
        real = [s for s in steps if not s.get("repeat")]
        done = [s for s in real if s["ok"]]
        failed = [s for s in real if not s["ok"] and not s.get("refused")]
        data_steps = [{"action": s["action"], "input": s["input"], "ok": s["ok"],
                       "observation": s["observation"]} for s in real]
        if question is not None:
            return {"text": question, "animation": "thinking", "needs_confirmation": False,
                    "proposal_id": None,
                    "data": {"agent_steps": data_steps, "status": "question"}}
        if final is None and not done:
            return None  # nothing achieved: let the router ask for clarification
        report_text = "\n".join(r.replace(" | ", "\n") for r in reports)
        if final is not None:
            text = final or "Done, bro."
            numbers = re.findall(r"\d+\.\d+|\d+%", report_text)
            already = numbers and sum(n in text for n in numbers) >= 0.6 * len(numbers)
            if report_text and report_text not in text and not already:
                text = f"{text}\n{report_text}"
            animation = "warn" if failed and not done else ("success" if done else "answering")
            status = "done"
        else:
            did = " ".join(dict.fromkeys(s["observation"] for s in done))
            last_err = failed[-1]["observation"] if failed else ""
            text = f"I got stuck, bro. Done so far: {did}"
            if last_err:
                text += f" Problem: {last_err}"
            if report_text:
                text += f"\n{report_text}"
            animation = "confused" if not done else "warn"
            status = "stuck"
        return {"text": text, "animation": animation, "needs_confirmation": False,
                "proposal_id": None, "data": {"agent_steps": data_steps, "status": status}}

    def _log(self, task: str, steps: list[dict[str, Any]], started: float,
             success: bool) -> None:
        if self.db is None:
            return
        try:
            AiRepo(self.db).log_call(
                timestamp=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                intent="agent", latency_ms=int((time.monotonic() - started) * 1000),
                success=success,
                prompt=task if self.config.get("ai", {}).get("logPrompts") else None)
        except Exception:
            logger.exception("agent ai_calls log failed")
