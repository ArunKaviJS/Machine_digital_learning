"""SystemAgent: this PC and Windows itself — specs/status (RAM, CPU,
battery…), the few read-only commands in cmd (systeminfo, ipconfig…),
Windows features (screenshot, volume, emoji, clipboard, virtual desktops)
and Settings pages. Never power / lock / credentials (not in any list)."""

from __future__ import annotations

import re

from backend.agents.base import AgentContext, AgentReply, AgentSpec, SubAgent

_DOMAIN = re.compile(
    r"\b(?:system|pc|computer|laptop|config\w*|spec\w*|ram|memory|cpu|processor|gpu|"
    r"battery|disk|storage|windows version|os|cmd|command prompt|powershell|terminal|"
    r"ip address|ip|network|ipconfig|systeminfo|tasklist|hostname|screenshot|snip|"
    r"volume|mute|unmute|emoji|clipboard|desktop|virtual desktop|magnif\w*|notifications?|"
    r"quick settings|widgets?|settings|bluetooth|wi-?fi|display|brightness|night light|"
    r"captions?|game bar|voice typing|play|pause|next song|previous song)\b")


# PC questions answered straight from system_info (live, the model asked for
# CPU info when the user asked about RAM, and took 25 s)
_TOPICS = [(re.compile(r"\b(?:ram|memory)\b"), "memory"),
           (re.compile(r"\b(?:cpu|processor)\b"), "cpu"),
           (re.compile(r"\b(?:gpu|graphics)\b"), "gpu"),
           (re.compile(r"\b(?:disk|storage|drive space|free space)\b"), "disk"),
           (re.compile(r"\b(?:battery|charging|charge)\b"), "battery"),
           (re.compile(r"\b(?:windows version|operating system|os)\b"), "os"),
           (re.compile(r"\b(?:config\w*|specs?|specifications?|hardware)\b"), "all")]
_QUESTION = re.compile(r"\b(?:how much|how many|what|which|check|show|tell|is|my|left)\b")
_NOT_A_QUESTION = re.compile(r"\b(?:settings?|open|cmd|command prompt|powershell|terminal|"
                             r"and|then|write|type)\b")


class SystemAgent(SubAgent):
    spec = AgentSpec(
        name="system",
        role="handle this PC and Windows itself: answer questions about the PC with "
             "system_info, run the allowed read-only commands in cmd, use Windows "
             "shortcuts (screenshot, volume, emoji...) and open Settings pages.",
        tools=frozenset({"system_info", "run_command", "open_app", "open_settings",
                         "windows_shortcut", "list_windows", "wait", "ask_user"}))
    domain = _DOMAIN

    def claim(self, session, text: str, ctx: AgentContext) -> AgentReply | None:
        """"how much RAM do I have", "check my battery": read it directly."""
        low = text.lower()
        if session.awaiting_answer or not _QUESTION.search(low) or _NOT_A_QUESTION.search(low):
            return None
        topics = list(dict.fromkeys(topic for regex, topic in _TOPICS if regex.search(low)))
        if not topics:
            return None
        topic = topics[0] if len(topics) == 1 else "all"
        ok, observation, report = session.tools.run("system_info", topic)
        reply = f"Here you go, bro:\n{(report or observation).replace(' | ', chr(10))}"
        session.add_tool_exchange(text, [("system_info", topic, observation)], reply)
        return AgentReply(text=reply, animation="success" if ok else "warn", agent=self.name,
                          steps=[{"action": "system_info", "input": topic, "ok": ok,
                                  "observation": observation}])
