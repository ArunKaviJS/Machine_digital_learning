"""The agent's tool catalog: every tool with its role, when to use it, its
input and an example — rendered into the system prompt so the model can
think about WHICH tool fits WHEN (ai/agent_prompts.py).

Also the two key catalogs the shortcut tools may use:
- WINDOWS_SHORTCUTS: Windows 11 shortcuts, by name (the model picks a name,
  the backend presses the keys — the model never sends raw key combos).
- APP_ACTIONS: per-app actions + a short "how to use" tip, shown to the model
  only when it OBSERVES the app in front with `app_actions`.

Left out on purpose (never in any list): lock / sign out / shut down /
restart / sleep, Win+R (Run), Win+X (power-user menu), Task Manager,
Ctrl+Alt+Del, password / credential screens, permanent delete, terminal
panels, and anything that sends a message for the user.

Pure data, no I/O (golden rule: Ollama chooses, backend decides).
"""

from __future__ import annotations

from typing import Any

# ---- tools: name -> role / when to use / input / example -------------------
# order = prompt order. `chat_only` tools exist only in the chat window.
TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "open_app", "role": "launch an installed app",
     "when": "the user wants an app, or a job needs one open first (before typing)",
     "input": "app name", "example": "notepad"},
    {"name": "close_app", "role": "close a running app politely (it may ask to save)",
     "when": "the user asks to close/quit an app", "input": "app name", "example": "chrome"},
    {"name": "focus_window", "role": "bring an already-open app to the front",
     "when": "the app is open but another window is in front", "input": "app name",
     "example": "word"},
    {"name": "type_text", "role": "type text into the app in front",
     "when": "the user gave words to write. Type their exact words",
     "input": "the exact text", "example": "how are you"},
    {"name": "press_key", "role": "press one plain key or a simple Ctrl combo",
     "when": "a single key is needed: enter, tab, escape, arrows, ctrl+s",
     "input": "key or combo", "example": "enter"},
    {"name": "app_actions", "role": "OBSERVE: list what the app in front can do "
     "(its actions + how to use it)",
     "when": "before doing something INSIDE an app (new tab, bold, save as, refresh...)",
     "input": "\"\"", "example": ""},
    {"name": "app_action", "role": "do one action from app_actions in the app in front",
     "when": "after app_actions showed the action you need",
     "input": "action name from app_actions", "example": "new_tab"},
    {"name": "windows_shortcut", "role": "use a Windows 11 shortcut",
     "when": "a Windows feature: screenshot, show desktop, snap window, emoji, "
             "clipboard history, virtual desktops, media/volume keys...",
     "input": "a shortcut name from the Windows shortcuts list", "example": "screenshot_snip"},
    {"name": "run_command", "role": "type ONE read-only command into the open Command "
     "Prompt / PowerShell and press Enter",
     "when": "the user asks to do something IN cmd/PowerShell (system configuration = "
             "systeminfo)",
     "input": "one of: systeminfo, ipconfig, ipconfig /all, tasklist, hostname, whoami, ver",
     "example": "systeminfo"},
    {"name": "open_settings", "role": "open a Windows Settings page",
     "when": "the user wants to SEE or CHANGE a setting themselves",
     "input": "page name", "example": "bluetooth"},
    {"name": "open_website", "role": "open a website in the browser",
     "when": "the user names a site or web address", "input": "address",
     "example": "youtube.com"},
    {"name": "system_info", "role": "read this PC's specs/status",
     "when": "a question ABOUT this computer (RAM, CPU, disk, battery, OS)",
     "input": "all / os / cpu / memory / disk / gpu / battery", "example": "all"},
    {"name": "list_windows", "role": "OBSERVE: list the apps open right now",
     "when": "you need to know what is open", "input": "\"\"", "example": ""},
    {"name": "wait", "role": "wait for an app to load",
     "when": "something was just opened and is not ready yet", "input": "seconds 1-5",
     "example": "2"},
    {"name": "ask_user", "role": "ask the user ONE short question", "chat_only": True,
     "when": "a detail you NEED is missing (which text, which app, which file)",
     "input": "the question", "example": "What should I write, bro?"},
    {"name": "finish", "role": "end the turn with a reply to the user",
     "when": "everything is done, it can't be done, or it's just chat/a question",
     "input": "short friendly reply", "example": "Done, bro."},
]

# ---- Windows 11 shortcuts ---------------------------------------------------
# name -> (keys, what it does, words that must appear in the request,
#          "window" = acts on the app we work in / "global")
WINDOWS_SHORTCUTS: dict[str, tuple[list[str], str, tuple[str, ...], str]] = {
    # desktop & windows
    "show_desktop": (["win", "d"], "show the desktop / bring windows back",
                     ("desktop",), "global"),
    "minimize_all": (["win", "m"], "minimize all windows", ("minimize all", "minimise all"),
                     "global"),
    "task_view": (["win", "tab"], "show all open windows and desktops",
                  ("task view", "all windows"), "global"),
    "switch_window": (["alt", "tab"], "switch to the previous window",
                      ("switch window", "switch app", "alt tab", "previous window"), "global"),
    "maximize_window": (["win", "up"], "maximize the window", ("maximize", "maximise"),
                        "window"),
    "minimize_window": (["win", "down"], "minimize the window", ("minimize", "minimise"),
                        "window"),
    "snap_left": (["win", "left"], "snap the window to the left half", ("left",), "window"),
    "snap_right": (["win", "right"], "snap the window to the right half", ("right",),
                   "window"),
    "snap_layouts": (["win", "z"], "open snap layouts", ("snap layout", "layout"), "window"),
    # virtual desktops
    "new_virtual_desktop": (["ctrl", "win", "d"], "create a new virtual desktop",
                            ("new desktop", "virtual desktop"), "global"),
    "next_desktop": (["ctrl", "win", "right"], "go to the next virtual desktop",
                     ("next desktop",), "global"),
    "previous_desktop": (["ctrl", "win", "left"], "go to the previous virtual desktop",
                         ("previous desktop",), "global"),
    "close_virtual_desktop": (["ctrl", "win", "f4"], "close this virtual desktop "
                              "(its windows move to the next one)", ("close desktop",),
                              "global"),
    # screen & capture
    "screenshot_snip": (["win", "shift", "s"], "snip part of the screen (Snipping Tool)",
                        ("screenshot", "snip", "screen shot", "capture"), "global"),
    "screenshot_full": (["win", "printscreen"], "save a full screenshot to Pictures\\Screenshots",
                        ("full screenshot", "save screenshot", "whole screen"), "global"),
    "magnifier_zoom_in": (["win", "="], "zoom the screen in (Magnifier)",
                          ("magnifier", "magnify", "zoom screen", "zoom in screen"), "global"),
    "magnifier_zoom_out": (["win", "-"], "zoom the screen out (Magnifier)",
                           ("magnifier", "zoom out screen"), "global"),
    "magnifier_close": (["win", "escape"], "close Magnifier", ("magnifier",), "global"),
    # panels
    "start_menu": (["win"], "open the Start menu", ("start menu", "start"), "global"),
    "search": (["win", "s"], "open Windows search", ("search",), "global"),
    "file_explorer": (["win", "e"], "open File Explorer", ("explorer", "my files"), "global"),
    "settings_app": (["win", "i"], "open Settings", ("settings",), "global"),
    "notifications": (["win", "n"], "open notifications and calendar",
                      ("notification", "calendar"), "global"),
    "quick_settings": (["win", "a"], "open quick settings (Wi-Fi, volume, brightness panel)",
                       ("quick settings", "quick panel"), "global"),
    "widgets": (["win", "w"], "open widgets (news, weather)", ("widget", "weather", "news"),
                "global"),
    "clipboard_history": (["win", "v"], "open clipboard history", ("clipboard",), "global"),
    "emoji_panel": (["win", "."], "open the emoji panel", ("emoji", "emoticon"), "global"),
    "voice_typing": (["win", "h"], "start voice typing", ("voice typing", "dictat"), "global"),
    "game_bar": (["win", "g"], "open Xbox Game Bar", ("game bar",), "global"),
    "live_captions": (["ctrl", "win", "l"], "turn live captions on/off", ("caption",),
                      "global"),
    # media & volume (keyboard media keys)
    "play_pause": (["media_play_pause"], "play / pause music or video",
                   ("play", "pause", "resume"), "global"),
    "next_track": (["media_next"], "next song / track", ("next song", "next track", "skip"),
                   "global"),
    "previous_track": (["media_prev"], "previous song / track",
                       ("previous song", "previous track", "last song"), "global"),
    "volume_up": (["volume_up"], "volume up a step", ("volume up", "louder", "increase volume"),
                  "global"),
    "volume_down": (["volume_down"], "volume down a step",
                    ("volume down", "quieter", "lower volume", "decrease volume"), "global"),
    "mute": (["volume_mute"], "mute / unmute sound", ("mute", "unmute"), "global"),
}

# ---- how to use each app -----------------------------------------------------
# app key -> processes, how-to tip, actions {name: (keys, what it does)}
_COMMON: dict[str, tuple[list[str], str]] = {
    "copy": (["ctrl", "c"], "copy the selection"),
    "cut": (["ctrl", "x"], "cut the selection"),
    "paste": (["ctrl", "v"], "paste"),
    "undo": (["ctrl", "z"], "undo the last change"),
    "redo": (["ctrl", "y"], "redo"),
    "select_all": (["ctrl", "a"], "select everything"),
    "save": (["ctrl", "s"], "save"),
    "find": (["ctrl", "f"], "find text"),
    "new": (["ctrl", "n"], "new document / window"),
    "open_file": (["ctrl", "o"], "open a file (shows the Open dialog)"),
    "print": (["ctrl", "p"], "print (shows the Print dialog)"),
    "zoom_in": (["ctrl", "="], "zoom in"),
    "zoom_out": (["ctrl", "-"], "zoom out"),
    "zoom_reset": (["ctrl", "0"], "reset zoom"),
}

_BROWSER = {
    "new_tab": (["ctrl", "t"], "open a new tab"),
    "close_tab": (["ctrl", "w"], "close this tab"),
    "reopen_tab": (["ctrl", "shift", "t"], "reopen the last closed tab"),
    "next_tab": (["ctrl", "tab"], "go to the next tab"),
    "previous_tab": (["ctrl", "shift", "tab"], "go to the previous tab"),
    "address_bar": (["ctrl", "l"], "go to the address bar (then type_text + enter)"),
    "refresh": (["f5"], "reload the page"),
    "back": (["alt", "left"], "go back"),
    "forward": (["alt", "right"], "go forward"),
    "new_window": (["ctrl", "n"], "open a new window"),
    "private_window": (["ctrl", "shift", "n"], "open a private / incognito window"),
    "history": (["ctrl", "h"], "open history"),
    "downloads": (["ctrl", "j"], "open downloads"),
    "bookmark_page": (["ctrl", "d"], "bookmark this page"),
    "full_screen": (["f11"], "full screen on/off"),
    "scroll_down": (["pagedown"], "scroll down a page"),
    "scroll_up": (["pageup"], "scroll up a page"),
    "top_of_page": (["home"], "go to the top"),
    "end_of_page": (["end"], "go to the bottom"),
}

APP_ACTIONS: dict[str, dict[str, Any]] = {
    "notepad": {
        "processes": ("notepad.exe",),
        "how": "Type with type_text. Each Notepad tab is a separate note.",
        "actions": {
            "new_tab": (["ctrl", "t"], "new note in a new tab"),
            "close_tab": (["ctrl", "w"], "close this note's tab"),
            "next_tab": (["ctrl", "tab"], "go to the next tab"),
            "save_as": (["ctrl", "shift", "s"], "save as (shows the Save dialog)"),
            "find_replace": (["ctrl", "h"], "find and replace"),
            "go_to_line": (["ctrl", "g"], "go to a line number"),
            "insert_time_date": (["f5"], "insert the current time and date"),
            "new_line": (["enter"], "start a new line"),
        },
    },
    "browser": {
        "processes": ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"),
        "how": "To visit a site: address_bar, type_text the address, press_key enter "
               "(or use open_website). To search the web: address_bar, type the words, enter.",
        "actions": _BROWSER,
    },
    "file_explorer": {
        "processes": ("explorer.exe",),
        "how": "To go to a folder: address_bar, type_text the path, press_key enter.",
        "actions": {
            "new_folder": (["ctrl", "shift", "n"], "create a new folder here"),
            "new_window": (["ctrl", "n"], "open a new File Explorer window"),
            "new_tab": (["ctrl", "t"], "open a new tab"),
            "close_tab": (["ctrl", "w"], "close this tab"),
            "address_bar": (["alt", "d"], "go to the address bar"),
            "search": (["ctrl", "e"], "search in this folder"),
            "rename": (["f2"], "rename the selected item (then type_text the name + enter)"),
            "refresh": (["f5"], "refresh"),
            "back": (["alt", "left"], "go back"),
            "forward": (["alt", "right"], "go forward"),
            "up_folder": (["alt", "up"], "go up one folder"),
            "properties": (["alt", "enter"], "show properties of the selected item"),
            "preview_pane": (["alt", "p"], "show/hide the preview pane"),
            "details_pane": (["alt", "shift", "p"], "show/hide the details pane"),
        },
    },
    "word": {
        "processes": ("winword.exe",),
        "how": "Type with type_text. Select text first (select_all) before formatting it.",
        "actions": {
            "bold": (["ctrl", "b"], "bold on/off"),
            "italic": (["ctrl", "i"], "italic on/off"),
            "underline": (["ctrl", "u"], "underline on/off"),
            "align_left": (["ctrl", "l"], "align left"),
            "align_center": (["ctrl", "e"], "center"),
            "align_right": (["ctrl", "r"], "align right"),
            "justify": (["ctrl", "j"], "justify"),
            "bigger_font": (["ctrl", "shift", "."], "bigger font"),
            "smaller_font": (["ctrl", "shift", ","], "smaller font"),
            "bullet_list": (["ctrl", "shift", "l"], "bullet list"),
            "page_break": (["ctrl", "enter"], "insert a page break"),
            "spell_check": (["f7"], "check spelling"),
            "save_as": (["f12"], "save as"),
        },
    },
    "excel": {
        "processes": ("excel.exe",),
        "how": "type_text into the selected cell, press_key enter to confirm, tab for the "
               "next cell. Formulas start with = e.g. =SUM(A1:A5).",
        "actions": {
            "edit_cell": (["f2"], "edit the selected cell"),
            "autosum": (["alt", "="], "insert SUM for the cells above"),
            "insert_date": (["ctrl", ";"], "insert today's date"),
            "bold": (["ctrl", "b"], "bold on/off"),
            "format_cells": (["ctrl", "1"], "open Format Cells"),
            "filter": (["ctrl", "shift", "l"], "turn filters on/off"),
            "select_column": (["ctrl", "space"], "select the column"),
            "select_row": (["shift", "space"], "select the row"),
            "new_sheet": (["shift", "f11"], "insert a new sheet"),
            "next_sheet": (["ctrl", "pagedown"], "go to the next sheet"),
            "previous_sheet": (["ctrl", "pageup"], "go to the previous sheet"),
        },
    },
    "powerpoint": {
        "processes": ("powerpnt.exe",),
        "how": "Type into the selected box with type_text.",
        "actions": {
            "new_slide": (["ctrl", "m"], "add a new slide"),
            "start_slideshow": (["f5"], "start the slideshow from the beginning"),
            "end_slideshow": (["escape"], "end the slideshow"),
            "next_slide": (["right"], "next slide (in a slideshow)"),
            "previous_slide": (["left"], "previous slide (in a slideshow)"),
            "bold": (["ctrl", "b"], "bold on/off"),
        },
    },
    "vs_code": {
        "processes": ("code.exe",),
        "how": "Type code with type_text in the editor. Use quick_open to open a file by name.",
        "actions": {
            "quick_open": (["ctrl", "p"], "open a file by name"),
            "command_palette": (["ctrl", "shift", "p"], "open the command palette"),
            "find_in_files": (["ctrl", "shift", "f"], "search all files"),
            "toggle_sidebar": (["ctrl", "b"], "show/hide the sidebar"),
            "comment_line": (["ctrl", "/"], "comment/uncomment the line"),
            "format_document": (["shift", "alt", "f"], "format the document"),
            "go_to_line": (["ctrl", "g"], "go to a line"),
            "close_editor": (["ctrl", "w"], "close this file's tab"),
            "split_editor": (["ctrl", "\\"], "split the editor"),
            "new_file": (["ctrl", "n"], "new file"),
        },
    },
    "calculator": {
        "processes": ("calculatorapp.exe", "calculator.exe"),
        "how": "type_text the sum, e.g. 12*7, then press_key enter. escape clears.",
        "actions": {
            "standard_mode": (["alt", "1"], "standard calculator"),
            "scientific_mode": (["alt", "2"], "scientific calculator"),
            "clear": (["escape"], "clear"),
            "equals": (["enter"], "calculate the result"),
            "history": (["ctrl", "h"], "show history"),
        },
    },
    "paint": {
        "processes": ("mspaint.exe",),
        "how": "Drawing needs the mouse, which I can't use. I can make a new picture, "
               "resize, save, undo.",
        "actions": {
            "resize": (["ctrl", "w"], "resize / skew the picture"),
            "new": (["ctrl", "n"], "new picture"),
            "save_as": (["f12"], "save as"),
        },
    },
    "media_player": {
        "processes": ("spotify.exe", "microsoft.media.player.exe", "wmplayer.exe", "vlc.exe"),
        "how": "play_pause / next_track / previous_track also work from windows_shortcut.",
        "actions": {
            "play_pause": (["space"], "play / pause"),
            "next_track": (["ctrl", "right"], "next track"),
            "previous_track": (["ctrl", "left"], "previous track"),
            "volume_up": (["ctrl", "up"], "volume up (Spotify)"),
            "volume_down": (["ctrl", "down"], "volume down (Spotify)"),
        },
    },
    "whatsapp": {
        "processes": ("whatsapp.exe", "whatsapp.root.exe"),
        "how": "I can open chats and search, but I never send messages for you: you "
               "press Enter to send.",
        "actions": {
            "new_chat": (["ctrl", "n"], "start a new chat (pick the contact yourself)"),
            "search_chats": (["ctrl", "f"], "search chats"),
        },
    },
}

# apps whose Enter = "send to someone": the agent must not press Enter there
SEND_ON_ENTER_APPS = {"whatsapp"}


def app_for_process(process_name: str | None) -> str | None:
    """'chrome.exe' -> 'browser'; unknown apps -> None (common actions only)."""
    proc = (process_name or "").lower()
    for key, info in APP_ACTIONS.items():
        if proc in info["processes"]:
            return key
    return None


def actions_for(app_key: str | None) -> dict[str, tuple[list[str], str]]:
    """The app's own actions first, then the common ones it doesn't override."""
    own = APP_ACTIONS[app_key]["actions"] if app_key else {}
    return {**own, **{k: v for k, v in _COMMON.items() if k not in own}}


def render_tools(chat: bool, only: set[str] | None = None) -> str:
    """Prompt text: one line per tool with role / when / input (`only` =
    a sub-agent's own tools)."""
    lines = []
    for spec in TOOL_SPECS:
        if spec.get("chat_only") and not chat:
            continue
        if only is not None and spec["name"] not in only:
            continue
        lines.append(f"- {spec['name']}: {spec['role']}. Use when: {spec['when']}. "
                     f"Input: {spec['input']}")
    return "\n".join(lines)


def render_shortcut_names() -> str:
    return ", ".join(WINDOWS_SHORTCUTS)


def tool_names(chat: bool) -> list[str]:
    return [s["name"] for s in TOOL_SPECS if chat or not s.get("chat_only")]
