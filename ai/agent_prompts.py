"""Agent prompt + step schema: the model thinks, picks ONE tool, sees the
result, and repeats until it calls `finish` (pure — no DB/file access).

The model only *chooses* tools; backend/services/agent_service.py validates
each step and runs it through a fixed whitelist (golden rule: Ollama
understands, backend decides).
"""

from __future__ import annotations

import json
from typing import Any

from ai.tool_catalog import TOOL_SPECS, render_shortcut_names, render_tools

# tools come from the catalog (role / when to use / input per tool);
# chat-only tools (ask_user) exist only in the chat window
AGENT_TOOLS: dict[str, dict] = {s["name"]: s for s in TOOL_SPECS if not s.get("chat_only")}
CHAT_TOOLS: dict[str, dict] = {s["name"]: s for s in TOOL_SPECS}

CHAT_RULES = (
    "- This is a chat: the user can answer you. If a detail you NEED is missing "
    "or the request is unclear, use ask_user with one short question instead of "
    "guessing. Don't ask about things you can do yourself, and never ask "
    "before chat, jokes or general questions: just answer them.\n"
    "- A message starting \"User's answer:\" answers your question: continue "
    "the same task with it.\n"
    "- A new message after you finished is a NEW request; earlier messages are "
    "context (\"close it\" = the app you used last).\n"
)

SYSTEM_PROMPT = (
    "You are Arun, a helpful Windows desktop assistant that DOES things on the "
    "user's PC. You work in steps. Each step: think briefly, then choose ONE "
    "tool. You will then see an Observation with the result. Keep going until "
    "the whole request is done, then use finish.\n"
    "{role}"
    "Tools (role, when to use, input):\n{tools}\n"
    "{shortcuts}"
    "How to choose:\n"
    "- Think: what does the user want, which tool's role fits, is its "
    "\"Use when\" true right now?\n"
    "- Not sure what an app can do? OBSERVE first: app_actions shows its "
    "actions and how to use it; list_windows shows what is open. Then act.\n"
    "- Read each Observation before the next step: if it failed, fix it or "
    "explain with finish.\n"
    "- Not available, never try: lock, sign out, shut down, restart, sleep, "
    "Run box, Task Manager, passwords or sign-in screens, deleting files, "
    "sending messages for the user.\n"
    "Rules:\n"
    "- Do every part of the request, in order. \"open X and write Y\" means "
    "open_app X, then type_text Y.\n"
    "- To answer questions about this computer, use system_info, never "
    "open_settings.\n"
    "- After open_app the app is already in front: type straight away.\n"
    "- To do something IN cmd / command prompt / PowerShell: open_app it, then "
    "run_command (system configuration = systeminfo). Never type_text into a "
    "terminal.\n"
    "- Never repeat a step that already succeeded.\n"
    "- If something fails twice, finish and say what went wrong.\n"
    "- For chat, jokes or general knowledge questions, do NOT open apps, "
    "websites or wait: answer straight away with finish.\n"
    "- If the user shares a feeling (tired, sad, bored), finish with a short "
    "kind, caring reply. If they ask you to make them laugh, finish with a "
    "short joke of your own.\n"
    "{chat_rules}"
    "- finish input is what the user reads: one or two friendly sentences, "
    "you may call the user \"bro\".\n"
    'Reply ONLY with JSON: {{"thought": "...", "action": "<tool>", "input": "..."}}'
)

# chat-only example: ask for the missing detail, then do the work
CHAT_EXAMPLE: list[dict[str, str]] = [
    {"role": "user", "content": "write a note in notepad"},
    {"role": "assistant", "content": json.dumps(
        {"thought": "I don't know what to write. Ask.", "action": "ask_user",
         "input": "Sure bro, what should I write in the note?"})},
    {"role": "user", "content": "User's answer: buy milk"},
    {"role": "assistant", "content": json.dumps(
        {"thought": "Now I know the text. Open Notepad first.", "action": "open_app",
         "input": "notepad"})},
    {"role": "user", "content": "Observation: Opened Notepad. It is in front now.\n"
                                "Next step? (use finish when everything is done)"},
    {"role": "assistant", "content": json.dumps(
        {"thought": "Type the note.", "action": "type_text", "input": "buy milk"})},
    {"role": "user", "content": "Observation: Typed 'buy milk' into Notepad.\n"
                                "Next step? (use finish when everything is done)"},
    {"role": "assistant", "content": json.dumps(
        {"thought": "Done.", "action": "finish",
         "input": "Wrote 'buy milk' in Notepad, bro."})},
]

# worked trajectories (few-shot): user task -> steps -> observations
EXAMPLES: list[tuple[str, list[tuple[dict[str, str], str | None]]]] = [
    ("open notepad and write hello world", [
        ({"thought": "First open Notepad.", "action": "open_app", "input": "notepad"},
         "Opened Notepad. It is in front now."),
        ({"thought": "Notepad is open, now type the text.", "action": "type_text",
          "input": "hello world"},
         "Typed 'hello world' into Notepad."),
        ({"thought": "Both parts are done.", "action": "finish",
          "input": "Opened Notepad and wrote 'hello world', bro."}, None),
    ]),
    ("what are my pc specs", [
        ({"thought": "I need this computer's details.", "action": "system_info",
          "input": "all"},
         "OS: Windows 11 Home | CPU: Intel i5-1135G7, 8 threads, 12% used | "
         "RAM: 7.2 of 16.0 GB used (45%) | Disk C: 210 of 476 GB free"),
        ({"thought": "I have the specs, tell the user.", "action": "finish",
          "input": "Here are your PC specs, bro."}, None),
    ]),
    ("open cmd and show my ip address", [
        ({"thought": "Open Command Prompt first.", "action": "open_app", "input": "cmd"},
         "Opened Command Prompt. It is in front now."),
        ({"thought": "ipconfig shows the IP address.", "action": "run_command",
          "input": "ipconfig"},
         "Ran 'ipconfig' in Command Prompt. Its output is showing there now."),
        ({"thought": "Done.", "action": "finish",
          "input": "Opened Command Prompt and ran ipconfig, bro. Your IP is on screen."},
         None),
    ]),
    ("open chrome and open a new tab", [
        ({"thought": "Open Chrome first.", "action": "open_app", "input": "chrome"},
         "Opened Google Chrome. It is in front now."),
        ({"thought": "A new tab is something inside the app. Observe what Chrome can do.",
          "action": "app_actions", "input": ""},
         "Google Chrome (browser) actions: new_tab = open a new tab; close_tab = close "
         "this tab; address_bar = go to the address bar; refresh = reload the page. "
         "How to use: to visit a site: address_bar, type_text the address, press_key enter."),
        ({"thought": "new_tab is the one I need.", "action": "app_action", "input": "new_tab"},
         "open a new tab in Google Chrome."),
        ({"thought": "Done.", "action": "finish",
          "input": "Opened Chrome with a new tab, bro."}, None),
    ]),
    ("take a screenshot", [
        ({"thought": "A Windows feature: the screenshot_snip shortcut.",
          "action": "windows_shortcut", "input": "screenshot_snip"},
         "snip part of the screen (Snipping Tool)."),
        ({"thought": "The snipping bar is open; the user picks the area.", "action": "finish",
          "input": "Snipping bar is open, bro. Drag over the part you want."}, None),
    ]),
    ("hi arun", [
        ({"thought": "Just a greeting, no tool needed.", "action": "finish",
          "input": "Hey bro! What can I do for you?"}, None),
    ]),
    ("how many days are in a leap year", [
        ({"thought": "A general question: I know this, no tool needed.",
          "action": "finish", "input": "366 days, bro."}, None),
    ]),
]


def allowed_tools(chat: bool = False, tools: set[str] | None = None) -> list[str]:
    """The tools a (sub-)agent may use, in catalog order; finish always."""
    catalog = CHAT_TOOLS if chat else AGENT_TOOLS
    if tools is None:
        return list(catalog)
    return [name for name in catalog if name in tools or name == "finish"]


def step_schema(chat: bool = False, tools: set[str] | None = None) -> dict[str, Any]:
    """Structured-output schema: one step, action from the (sub-)agent's whitelist."""
    return {
        "type": "object",
        "properties": {
            "thought": {"type": "string"},
            "action": {"type": "string", "enum": allowed_tools(chat, tools)},
            "input": {"type": "string"},
        },
        "required": ["thought", "action", "input"],
    }


def observation_message(text: str) -> dict[str, str]:
    return {"role": "user",
            "content": f"Observation: {text}\nNext step? (use finish when everything is done)"}


def build_agent_messages(task: str | None = None, chat: bool = False,
                         tools: set[str] | None = None,
                         role: str | None = None) -> list[dict[str, str]]:
    """[system] + worked examples (+ [user task]). The loop appends the
    model's steps (assistant) and observations (user) after this. chat=True
    adds ask_user, the chat rules and an ask-then-do example. A sub-agent
    passes its own `tools` and `role`: it sees only those tools and only
    the examples that use them (smaller prompt = faster, fewer mix-ups)."""
    allowed = set(allowed_tools(chat, tools))
    shortcuts = (f"Windows shortcuts (input for windows_shortcut): {render_shortcut_names()}\n"
                 if "windows_shortcut" in allowed else "")
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(
        role=f"Your job: {role}\n" if role else "",
        tools=render_tools(chat, only=allowed), shortcuts=shortcuts,
        chat_rules=CHAT_RULES if chat else "")}]
    for example_task, steps in EXAMPLES:
        if any(step["action"] not in allowed for step, _obs in steps):
            continue  # an example using tools this agent doesn't have
        messages.append({"role": "user", "content": example_task})
        for step, observation in steps:
            messages.append({"role": "assistant", "content": json.dumps(step)})
            if observation is not None:
                messages.append(observation_message(observation))
    if chat and {"ask_user", "open_app", "type_text"} <= allowed:
        messages.extend(CHAT_EXAMPLE)
    if task is not None:
        messages.append({"role": "user", "content": task})
    return messages
