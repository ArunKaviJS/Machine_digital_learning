# SKILL: Arun, a local AI desktop companion (Windows 11)

> READ THIS FILE FIRST, then read `CONTEXT.md`. This file is the **stable spec** (what to build and why).
> `CONTEXT.md` is the **live progress log** (what is done, what is next). Never skip either.

---

## 0. Rules for any AI agent working on this project

1. **Read `SKILL.md`, then `CONTEXT.md`.** Do not re-explore the whole repo; use the File Inventory in `CONTEXT.md`.
2. **Continue from "NEXT ACTION" in `CONTEXT.md`.** Do not redo anything marked DONE.
3. **Update `CONTEXT.md` after EVERY completed unit of work** (one file, one service, one test pass), not at the end. The session can die at any time, since the user is on a free plan with limited tokens. Update means: status board, file inventory, session log entry, NEXT ACTION.
4. **Small units.** Build one milestone at a time, with tests. Prefer many small files over one large one.
5. **Do not add features outside the current milestone** without recording it in `CONTEXT.md` under "Ideas / Parked".
6. If a decision conflicts with this spec, **write the change in `CONTEXT.md` > Decisions** with the reason. Do not silently deviate.
7. Never hard-code secrets or paths. Everything configurable goes in `config.json`.
8. Keep answers/code compact. Do not paste whole files back into chat unless asked.

---

## 1. What Arun is

A 3D-cartoon character in a transparent, borderless, always-on-top window on the Windows desktop. It:

- reminds the user to drink water (45 min default) and records glasses,
- tracks time spent per app and per website (YouTube, Instagram, etc.), nags, counts down and closes the distracting tab,
- answers questions about usage/water/productivity (quick questions + typed questions),
- tidies folders (e.g. Downloads) after confirmation, with undo.

It is adapted from the "Bro" desktop-companion guide. **Changes from the original:** renamed Bro → **Arun**, **no voice** (no STT/TTS), **no Sarvam / no GPT / no cloud AI**, local **Ollama** model instead, **Windows 11 only for v1**, backend/AI/client separated into folders.

## 2. Golden rule

> **Ollama understands. Backend decides. Database knows. UI displays.**

- The LLM **never** computes numbers, reads the DB, touches files, or triggers OS actions.
- The LLM is used **only** to convert unrecognised natural language into a **strict intent JSON**. After that the model is unloaded (`keep_alive: 0`) and not used again for that request.
- Answers come from **templates filled with real DB data** (v1). A second LLM call to rephrase is optional and OFF by default (Option B, later).
- Most of the app works with **Ollama not installed at all**. AI features degrade gracefully.

## 3. High-level architecture

```
┌──────────────┐  HTTP + WebSocket (127.0.0.1)  ┌────────────────────────────────┐
│ CLIENT (Qt)  │ ─────────────────────────────► │ BACKEND (FastAPI)              │
│ character,   │ ◄───────────────────────────── │  api/ services/ tracker/       │
│ menu, popups │      events (push)             │  scheduler/ router/ db/ os/    │
└──────────────┘                                └───────┬───────────────┬────────┘
                                                        │ SQLite        │ HTTP (only on router miss)
                                                        ▼               ▼
                                                   arun.db        ┌───────────┐   ┌────────┐
                                                                  │ AI module │──►│ Ollama │
                                                                  │ (ai/)     │   └────────┘
                                                                  └───────────┘
```

- **Client**: draws the character, plays pose animations, shows the menu/popups/chat box. **No business logic.** It sends IDs/text to the backend and renders the response.
- **Backend**: all logic. Works with or without AI.
- **AI module** (`ai/`): thin wrapper around Ollama: prompt, call, parse, validate. No access to DB or files.
- **OS integration** (`backend/os_integration/`): behind an interface so macOS can be added later.

Process model (v1): `run.py` starts the backend in a background thread (uvicorn bound to `127.0.0.1` only), waits for `/health`, then starts the Qt client. `python -m backend.main` also runs the backend standalone for testing/dev.

## 4. Technology decisions

| Area | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | one language for all parts |
| Backend | FastAPI + uvicorn, pydantic v2 | localhost only |
| DB | SQLite (`sqlite3` + small repository classes) | file: `%APPDATA%\Arun\arun.db` |
| Scheduler | asyncio tasks (or APScheduler) | water + guard + tracker poll |
| Windows APIs | `ctypes` (user32/kernel32/shell32) + `psutil` | no pywin32 needed |
| Client UI | **PyQt6** (per-pixel alpha, no jagged edges). Fallback: tkinter `-transparentcolor` | see CONTEXT decisions |
| Images | Pillow; assets prepared with ffmpeg + rembg | see `need-to-do.md` |
| LLM runtime | **Ollama installed natively** (no Docker) | |
| LLM model | `qwen2.5:0.5b` default (~400 MB); upgrade `qwen2.5:1.5b` if intent parsing is weak | configurable |
| HTTP client | httpx | Ollama calls |
| Tests | pytest | inject fake clock + fake OS adapter |
| Packaging | PyInstaller `--noconsole` (late milestone) | |

## 5. Folder structure

```
arun/
├── SKILL.md              # this file (stable spec)
├── CONTEXT.md            # live progress + handoff
├── need-to-do.md         # manual tasks for the human
├── run.py                # launcher: backend thread + client
├── requirements.txt      # backend + client + ai deps
├── config.default.json   # defaults (user copy lives in %APPDATA%\Arun\config.json)
├── backend/
│   ├── main.py           # FastAPI app factory, startup/shutdown
│   ├── config.py         # load/merge/validate config
│   ├── api/              # routers: ask.py quick.py water.py usage.py tidy.py settings.py events.py
│   ├── services/         # usage_service.py stats_service.py water_service.py tidy_service.py guard_service.py
│   ├── router/           # question_router.py, rules.py (patterns), templates.py (response text)
│   ├── tracker/          # activity_tracker.py (poll loop, session lifecycle), classifier.py
│   ├── scheduler/        # scheduler.py (water + guard ticks)
│   ├── db/               # connection.py, schema.sql, migrations.py, repositories/
│   ├── os_integration/   # base.py (interface), windows.py (impl), factory.py
│   └── events.py         # in-process event bus -> WebSocket push
├── ai/
│   ├── gateway.py        # single entry: parse_intent(text) -> Intent | None
│   ├── ollama_client.py  # HTTP call, timeout, keep_alive=0, single-flight lock
│   ├── prompts.py        # system prompt + few-shot examples
│   └── schemas.py        # Intent pydantic models + allowed enums
├── client/
│   ├── app.py            # Qt app entry
│   ├── character_window.py  # transparent window, animation player, walking
│   ├── menu.py           # click menu
│   ├── panels/           # quick_questions.py ask_box.py water.py usage.py settings.py
│   ├── popups.py         # water popup, nag bubble, countdown
│   └── api_client.py     # HTTP + WebSocket client to backend
├── assets/stickers/arun/ # <pose>.png or <pose>/0001.png ... frames
├── tools/                # import_character.py (rembg + ffmpeg + find-loop)
└── tests/
```

## 6. Startup flow

```
run.py
  → load config (create defaults if missing)
  → init DB (run migrations)
  → start backend services: tracker, scheduler (water + guard), event bus
  → wait for /health
  → start client (character appears, idle/walk)
```
No LLM work happens at startup. Ollama is never pinged until the router needs it (an optional "AI available?" check may run lazily from the Settings screen).

## 7. Interaction flow

```
Click Arun → reaction animation + predefined greeting "Hey bro! 👋" (no AI) → menu:
  Quick Questions ▼ | Ask a Question | 💧 Water | 📊 My Usage | ⚙ Settings
```

- **Quick Question** → client sends `question_id` → backend maps ID → service → SQLite → template → response. **No AI. No router.**
- **Ask a Question** → client sends free text → **Question Router**:
  1. pending-confirmation check ("yes"/"no"/"undo" against pending state),
  2. rule-based matching (patterns, aliases, period words),
  3. if intent AND all required slots resolved → execute (no AI),
  4. else → `ai.gateway.parse_intent(text)` → validate → execute,
  5. else → clarification message.
- Other menu items (Water, Usage, Settings) call backend endpoints directly.

## 8. Quick Questions catalogue (IDs are contract, do not rename)

| ID | Label | Service call |
|---|---|---|
| `youtube_usage_today` | How much YouTube did I use today? | usage(site=youtube.com, today) |
| `youtube_usage_yesterday` | How much YouTube did I use yesterday? | usage(youtube.com, yesterday) |
| `youtube_usage_week` | How much YouTube did I use this week? | usage(youtube.com, this_week) |
| `top_app_today` | What app did I use the most today? | top_app(today) |
| `top_app_week` | What app did I use the most this week? | top_app(this_week) |
| `screen_time_today` | How much screen time did I have today? | screen_time(today) |
| `longest_session_today` | What was my longest session? | longest_session(today) |
| `most_active_hour_today` | When was I most active today? | most_active_hour(today) |
| `compare_today_yesterday` | How does today compare with yesterday? | compare_days(today, yesterday) |
| `water_today` | How much water did I drink today? | water_today() |
| `last_water_reminder` | When was my last water reminder? | last_water_reminder() |

Categories for the UI: USAGE, PRODUCTIVITY, WATER. `GET /quick-questions` returns this list from the backend (single source of truth).

## 9. Intent schema (the ONLY thing the LLM may output)

```json
{ "intent": "<enum>", "application": "<string|null>", "period": "<enum|null>",
  "comparison": "<enum|null>", "folder": "<string|null>" }
```

| Field | Allowed values |
|---|---|
| `intent` | `usage_query`, `compare_usage`, `top_app`, `screen_time`, `longest_session`, `most_active_hour`, `compare_days`, `water_status`, `log_water`, `last_water_reminder`, `tidy_folder`, `undo_tidy`, `unknown` |
| `period` | `today`, `yesterday`, `this_week`, `last_week`, `last_7_days`, `this_month` |
| `comparison` | `average`, `yesterday`, `last_week`, `none` |
| `application` | must be in tracked list (config) or `any`; aliases resolved by backend (yt → youtube.com) |
| `folder` | one of known folder keys: `downloads`, `desktop`, `documents`, `pictures`, `videos` (no free paths from the LLM) |

Backend validation (mandatory): enum membership, application in tracked list, folder key in whitelist, required slots per intent. Invalid → clarification, never execute. Required slots: `usage_query` (application; period defaults to `today`), `compare_usage` (application, period; comparison defaults `average`), `top_app`/`screen_time`/`longest_session`/`most_active_hour` (period default `today`), `tidy_folder` (folder).

## 10. Rule-based router (no AI)

Normalise: lowercase, strip punctuation and filler ("bro", "arun", "please", "hey"). Match:

- **Aliases**: `yt|youtube|you tube` → youtube.com; `insta|instagram|ig` → instagram.com.
- **Period words**: `today`, `yesterday`, `this week`, `last week`, `past 7 days`, `this month`. Default `today`.
- **Intent keywords**:
  - usage: `how much|how long|how many (hours|minutes)|time spent|used` + app
  - compare: `compare|more than|less than|normal|usual|average|vs|than` + app
  - top app: `most used|used the most|top app`
  - screen time: `screen time`
  - water: `water|drink|glass` (+ `drank|had|just` → `log_water`)
  - tidy: `tidy|organi[sz]e|clean|sort` + folder alias
  - undo: `undo|put back|revert`
  - confirm: `yes|yep|ok|confirm|do it` / `no|cancel|stop` (only valid when a proposal is pending)
- Ambiguity rule: if two intents score equally, or a compare-style phrase is present without a clear app/period, **hand off to AI**.
- Keep patterns in `router/rules.py` as data tables so they are easy to extend and unit-test.

## 11. AI module contract

- `ai.gateway.parse_intent(text: str) -> Intent | None`
- Ollama request (`POST http://localhost:11434/api/chat`):
  - `model` from config, `stream: false`, `format: "json"`, **`keep_alive: 0`**,
  - `options`: `temperature: 0`, `num_predict: 120`, `num_ctx: 1024`.
- **Single-flight**: one lock/queue; a second request waits or returns "busy".
- **Timeout** (default 15 s; first call after unload may take 1–3 s to reload). On timeout/connection error/invalid JSON → return `None` → backend says "I couldn't understand that, bro. Try a Quick Question."
- Prompt: short system prompt + ~8 few-shot examples; list the allowed enums; "Respond ONLY with JSON; use `unknown` if unsure; never answer the question."
- User text is truncated (e.g. 300 chars). Output is never trusted: always pydantic-validated + whitelist-checked.
- AI is disabled when `ai.enabled=false`; router then goes straight to clarification.
- Log each AI call (time, latency, success) into `ai_calls` table for tuning. Do not store user text unless `ai.logPrompts=true`.
- Optional later (Option B): phrase an answer from facts; weekly summary; nag-message variants (generate once, cache).

## 12. Database (SQLite)

Timestamps: ISO-8601 local time with offset; also store local `date` (YYYY-MM-DD) for fast grouping.

```sql
usage_sessions(
  id INTEGER PK, application TEXT NOT NULL,   -- e.g. 'Chrome', 'Code', 'Spotify'
  website TEXT NULL,                          -- matched tracked site, e.g. 'youtube.com'
  window_title TEXT NULL,                     -- only if config.storeTitles=true
  start_time TEXT NOT NULL, end_time TEXT NOT NULL,
  duration_seconds INTEGER NOT NULL, date TEXT NOT NULL)
water_events(
  id INTEGER PK, timestamp TEXT NOT NULL, date TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('reminder_shown','drank','snoozed','dismissed')))
tidy_batches(
  id INTEGER PK, folder TEXT, created_at TEXT, confirmed INTEGER, undone INTEGER DEFAULT 0)
tidy_moves(
  id INTEGER PK, batch_id INTEGER REFERENCES tidy_batches(id),
  original_path TEXT, new_path TEXT, moved_at TEXT, undone INTEGER DEFAULT 0)
guard_events(
  id INTEGER PK, timestamp TEXT, date TEXT, site TEXT,
  type TEXT CHECK(type IN ('nag','countdown_start','tab_closed','cancelled','snoozed')))
ai_calls(id INTEGER PK, timestamp TEXT, intent TEXT, latency_ms INTEGER, success INTEGER)
meta(key TEXT PRIMARY KEY, value TEXT)        -- schema_version, etc.
```
Indexes: `usage_sessions(date)`, `usage_sessions(website, date)`, `water_events(date)`.
Use a `schema_version` migration mechanism from day one.

## 13. Services (backend)

- **UsageService**: `usage(site|app, period)`, `top_app(period)`, `screen_time(period)`, `longest_session(period)`, `most_active_hour(period)`.
- **StatsService**: `compare_days(a, b)`, `average_daily(site, days=7)` (exclude today), `compare_usage(site, period, comparison)`. Period → date range helper lives here (one place, unit-tested, week starts Monday).
- **WaterService**: `drank()`, `snooze()`, `today_count()`, `last_reminder()`, `next_due()`.
- **GuardService**: distraction state machine (§15).
- **TidyService**: `propose(folder_key)`, `confirm(proposal_id)`, `undo_last()`.
- **QuestionRouter**: §7/§10.
- **NotificationManager**: pushes events to the client over WebSocket.
- All services take `clock` and `os_adapter` via constructor injection (testability).

## 14. Activity tracking (Windows)

Poll every `pollSeconds` (default 2):

1. `get_foreground_window()` → `{hwnd, pid, process_name, title}`.
2. If the foreground process is **Arun itself** → ignore this tick (keep the previous state; clicking Arun must not break a YouTube session).
3. `get_idle_seconds()`; if idle ≥ `idleThresholdSeconds` (default 120) → close the current session (user is away).
4. Classify: if process ∈ browsers (`chrome.exe`, `msedge.exe`, `brave.exe`, `firefox.exe`, `opera.exe`, `vivaldi.exe`) and title matches a tracked site's title keywords → `website` set. Application = friendly process name.
5. Session lifecycle: same (application, website) as previous tick → extend; different → close old + open new. Gaps > `maxGapSeconds` (system sleep) are clamped, never counted.
6. Sessions spanning midnight are **split** at 00:00.
7. Flush the open session on shutdown.
8. `trackAllApps` (default true) records every app for "most used app"; `false` records tracked sites only.

Windows can only see **window titles**, not URLs. Site matching map (config):
```json
"siteMatchers": { "youtube.com": ["YouTube"], "instagram.com": ["Instagram"] }
```
Known weakness: a tab titled "YouTube" in the background is not detected; only the active tab counts. A browser extension is the future fix (see Enhancements).

## 15. Distraction guard state machine

```
IDLE ──(tracked site active)──► TRACKING
TRACKING ──(streak ≥ nagAfterMinutes)──► NAGGING   (warn pose + bubble; repeat every nagRepeatSeconds)
NAGGING ──(streak ≥ closeAfterMinutes)──► COUNTDOWN (warningSeconds countdown, visible, with [Cancel/5 more min])
COUNTDOWN ──(expires AND foreground still matches)──► CLOSING (leap animation, Ctrl+W, angry pose)
CLOSING ──► COOLDOWN ──► IDLE
any state ──(away from tracked sites ≥ breakResetMinutes)──► streak resets → IDLE
```
- **Streak** = accumulated seconds on tracked sites since the last break of ≥ `breakResetMinutes`.
- **Safety before Ctrl+W (mandatory):** re-read the foreground window; proceed only if the process is a browser **and** title still matches the same site. Otherwise cancel and log `cancelled`.
- Arun's window must be **non-activating** so the browser keeps focus and Ctrl+W goes to it.
- Do not nag/close when DND is active: fullscreen app, presentation mode, screen share/meeting app (config list), or manual pause.
- Demo mode (`demoMode=true`): nag 10 s, countdown from 20 s, close at 30 s, repeat 5 s, break reset 30 s.

## 16. Water reminder

Timer: next reminder = max(last drink, last reminder) + `waterIntervalMinutes`. On due (and not DND/idle/locked): push event → water pose + popup "Time to drink water!" with **YES** / **Remind me later** (snooze 10 min). YES → `water_events(drank)`, happy pose, jump. Daily target (`waterDailyTarget`, default 8) shown in Water panel. No AI.

## 17. Folder tidy

Categories by extension (config-overridable): Images, Videos, Audio, Documents, Archives; everything else stays. Flow: propose (counts only; nothing moves) → user confirms → move → log each move in `tidy_moves` → `undo_last()` reverses the latest non-undone batch.
Rules: only the top level of the folder (no recursion); skip folders, hidden/system files, files modified in the last 60 s (likely downloading: `.crdownload`, `.part`, `.tmp`); resolve name collisions with `name (1).ext`; refuse paths outside whitelisted folder keys; never delete anything.

## 18. API surface (backend, all on 127.0.0.1)

| Method & path | Purpose |
|---|---|
| `GET /health` | liveness + ai status |
| `GET /quick-questions` | catalogue (§8) |
| `POST /ask/quick` `{question_id}` | quick question answer |
| `POST /ask` `{text}` | free text → router |
| `POST /water/drink` · `POST /water/snooze` · `GET /water/today` | water |
| `GET /usage/summary?period=` | data for the My Usage panel |
| `POST /tidy/propose` `{folder}` · `POST /tidy/confirm` `{proposal_id}` · `POST /tidy/undo` | tidy |
| `GET /settings` · `PUT /settings` | config read/update (validated) |
| `WS /ws/events` | server→client push: `water_due`, `nag`, `countdown_tick`, `tab_closed`, `animation`, `notice` |

**Response envelope** (every answer):
```json
{ "text": "You spent 2h 35m on YouTube yesterday, about 1h more than your usual.",
  "animation": "warn", "needs_confirmation": false, "proposal_id": null, "data": {} }
```
`animation` ∈ `idle, walk, smile, wave, warn, angry, happy, water`.

## 19. Response templates (v1, no LLM)

Kept in `router/templates.py`, keyed by intent, filled with DB values. Duration formatter: `155 → "2h 35m"`, `45 → "45m"`, `0 → "0m"`. Tone: friendly, short, calls the user "bro" occasionally. Choose animation by result (e.g. above-average usage → `warn`, low usage → `happy`).
Example: `"You spent {dur} on {site} {period_label}, about {diff} {more_less} than your usual daily average."`

## 20. Client (PyQt6) requirements

- Window flags: `FramelessWindowHint | WindowStaysOnTopHint | Tool | WindowDoesNotAcceptFocus`; `WA_TranslucentBackground`; `WA_ShowWithoutActivating`. Also set `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` via ctypes.
- Animation player: loads `assets/stickers/arun/<pose>.png` or numbered frames at `fps` (default 24); caches `QPixmap`s; mirrors horizontally when walking left; scales by **height** (200–260 px) so poses don't shrink.
- Walking: along the bottom of the monitor's **work area** (above the taskbar), multi-monitor and DPI aware. When the menu/chat is open: stop wandering, dock the panel next to Arun, move both when either is dragged.
- Click vs drag distinction; right-click context menu: Remind me to drink now, Pause Arun (DND), Clear chat, Start at login, Quit.
- All network calls run off the UI thread (QThread/worker) and return via signals.
- Needs an Edit-style paste support in text boxes (standard Qt widgets already do).
- Single-instance lock (mutex/lock file).

## 21. Config (`%APPDATA%\Arun\config.json`)

```json
{
  "userName": "YourName", "character": "arun", "walking": true, "walkFacesRight": true, "fps": 24,
  "waterIntervalMinutes": 45, "waterDailyTarget": 8, "waterSnoozeMinutes": 10,
  "distractingSites": ["youtube.com", "instagram.com"],
  "siteMatchers": { "youtube.com": ["YouTube"], "instagram.com": ["Instagram"] },
  "nagAfterMinutes": 15, "closeAfterMinutes": 25, "warningSeconds": 60,
  "nagRepeatSeconds": 120, "breakResetMinutes": 10, "closeMode": "tabs",
  "pollSeconds": 2, "idleThresholdSeconds": 120, "trackAllApps": true, "storeTitles": false,
  "dndApps": ["zoom.exe", "teams.exe", "ms-teams.exe"],
  "demoMode": false,
  "ai": { "enabled": true, "host": "http://localhost:11434", "model": "qwen2.5:0.5b",
          "timeoutSeconds": 15, "keepAlive": 0, "logPrompts": false }
}
```
Settings screen groups: Character, Water, Distraction, AI (matches the user's flow, step 23).

## 22. Windows APIs used (all via `ctypes`, no keys needed)

| Need | API |
|---|---|
| Active window | `user32.GetForegroundWindow` |
| Window title | `user32.GetWindowTextW` (+ `GetWindowTextLengthW`) |
| Process of window | `user32.GetWindowThreadProcessId` → `psutil.Process(pid).name()` |
| Idle time | `user32.GetLastInputInfo` + `kernel32.GetTickCount` |
| Fullscreen / presentation / busy | `shell32.SHQueryUserNotificationState` |
| Close tab | `user32.keybd_event` (or `SendInput`) Ctrl down, `W`, Ctrl up |
| Non-focus overlay window | `SetWindowLongW` with `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` |
| Start at login | `winreg` → `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` |
| Work area (above taskbar) | Qt `screen.availableGeometry()` |

All wrapped in `backend/os_integration/windows.py` implementing the interface in `base.py`:
`get_foreground_window()`, `get_idle_seconds()`, `is_dnd_active()`, `send_close_tab()`, `set_autostart(bool)`.

## 23. Edge cases the implementation must handle

- Ollama not installed/running → AI features say so; everything else works.
- Model reload latency after `keep_alive:0`; show a "thinking…" bubble in the client.
- Midnight rollover, sleep/hibernate gaps, system clock changes, DST.
- App closed abruptly → on next start, close any dangling session with its last heartbeat time (write a `heartbeat` to `meta` every poll or every 30 s).
- Windows lock screen: foreground may be empty → treat as idle.
- Multiple monitors, DPI scaling, taskbar position/auto-hide.
- Private/incognito windows have different titles; document the limitation.
- Notification spam: never stack more than one popup; queue events.
- Pending confirmation expires after 2 minutes.
- Privacy: all data local; server bound to 127.0.0.1; no telemetry; titles not stored by default; "Clear all data" option.

## 24. Build order (milestones)

| # | Milestone | Done when |
|---|---|---|
| M0 | Scaffold: folders, config loader, `run.py`, requirements, logging | `python run.py --backend-only` starts and `/health` works |
| M1 | DB layer: schema, migrations, repositories | tests pass on temp DB |
| M2 | OS integration (Windows): foreground, idle, DND, close-tab | manual script + unit tests with fake adapter |
| M3 | Activity tracker: sessions, midnight split, idle, Arun-ignore | simulated ticks produce correct rows |
| M4 | Usage + Stats services, period helper | tests for each quick-question query |
| M5 | Quick Questions API + templates | `/ask/quick` returns correct text for all 11 IDs |
| M6 | Rule-based router + pending-confirmation state | table-driven tests on ~40 phrases |
| M7 | AI module + gateway + validation | works with Ollama running; clean fallback when off |
| M8 | Water service + scheduler + events | reminder → drink → DB row |
| M9 | Distraction guard + demo mode | state machine tests with fake clock; live demo closes a tab |
| M10 | Tidy service + undo | propose/confirm/undo tests in a temp dir |
| M11 | Client: character window, animations, walking | transparent, always-on-top, non-focus |
| M12 | Client: menu, quick questions, ask box, popups, water/usage/settings panels | full flow in §7 works |
| M13 | Packaging (PyInstaller), autostart, single instance | `Arun.exe` runs on a clean profile |
| M14 | Enhancements (§25), polish, docs | per CONTEXT.md |

Backend (M0–M10) is built and tested **without any UI**, using pytest and `curl`/Swagger (`/docs`). The client comes after, so progress is verifiable and cheap in tokens.

## 25. Enhancements and gaps found in the original guide

Not in v1 unless promoted in CONTEXT.md:

- Whitelist/allow-list (YouTube for tutorials is not doomscrolling): e.g. title keywords or a "study mode" session.
- Focus mode / Pomodoro (Arun blocks tracked sites during a session).
- Browser extension (Chrome/Edge) sending the exact URL to `POST /tracker/url`, which fixes the window-title limitation.
- Dashboard (daily/weekly charts), streaks and goals, weekly AI summary (Option B).
- 20-20-20 eye-break, posture/stretch reminders.
- Per-site limits, "snooze with reason", per-app limits.
- Better AI: cached nag-message variants; optional answer phrasing with facts.
- macOS adapter behind the same OS interface.
- Original-guide weaknesses to avoid: Ctrl+W hitting the wrong window (solved by §15 safety check), no persistence (solved by SQLite), no DND (solved by §15/§23), no tests/logging (pytest + rotating log file in `%APPDATA%\Arun\logs`).

## 26. Coding conventions

- Type hints everywhere; pydantic models for API I/O; no global singletons (use a small `AppContext`).
- Pure functions for period math, formatting, rule matching so they are trivially testable.
- No blocking calls in async handlers; the Ollama call is `async` with timeout.
- Logging via `logging` to a rotating file; never log API keys or full window titles (unless `storeTitles`).
- Each module ≤ ~250 lines; split otherwise.
- Every new service ships with a test file in `tests/`.
