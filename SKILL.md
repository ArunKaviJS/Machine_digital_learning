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

A cartoon **water-droplet** character ("Bro" mascot) in a transparent, borderless, always-on-top window on the Windows desktop. It **lives in the system tray** and appears only when called (tray click / global hotkey) or when it has something to say. It:

- reminds the user to drink water (45 min default) and records glasses,
- tracks time spent per app and per website (YouTube, Instagram, etc.), nags, counts down and closes the distracting tab,
- answers questions about usage/water/productivity (quick questions + typed questions),
- tidies folders (e.g. Downloads) after confirmation, with undo,
- **opens** installed apps / websites / Windows Settings pages and **closes** apps or YouTube/Instagram tabs on request (§16c),
- asks "shall I close it?" about apps left open but unused for 30 min, and closes only on yes (§16b).

It never needs admin rights and never changes system settings (no Wi-Fi/Bluetooth toggles, no network passwords).

It is adapted from the "Bro" desktop-companion guide. **Changes from the original:** renamed Bro → **Arun**, **no voice** (no STT/TTS), **no Sarvam / no GPT / no cloud AI**, local **Ollama** model instead, **Windows 11 only for v1**, backend/AI/client separated into folders.

## 2. Golden rule

> **Ollama understands. Backend decides. Database knows. UI displays.**

- The LLM **never** computes numbers, reads the DB, touches files, or triggers OS actions. It may *name* an app or Settings page in `target`; the backend alone decides whether that app exists and opens/closes it.
- The LLM is used **only** to convert unrecognised natural language into a **strict intent JSON** (Ollama structured outputs constrain it to the schema). It is not used again for that request. The model stays warm for `ai.keepAlive` (default `"5m"`) to avoid an ~8 s reload per call.
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
| LLM model | `qwen2.5:0.5b-instruct` default (~400 MB); upgrade `qwen2.5:1.5b` if intent parsing is weak | configurable |
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
├── ai/                   # pure Ollama wrapper: no DB or file access (golden rule)
│   ├── ollama_client.py  # HTTP call, timeout, keep_alive=0, single-flight lock
│   └── prompts.py        # system prompt + few-shot examples
│   # backend/services/ai_gateway.py (not in ai/): OllamaGateway.parse_intent(text)
│   # -> Intent | None; validates + logs to ai_calls (needs DB, so it lives in backend/)
├── client/
│   ├── app.py            # Qt app entry: single instance, tray, hotkey
│   ├── character_window.py  # transparent window, presence, reactions, WS event handling
│   ├── placeholder_svg.py   # animated water-droplet character (until real art exists)
│   ├── popups.py         # water popup, question popup, guard banner, CommandsPanel (right-click)
│   ├── tray.py           # system-tray icon (Call / Quit)
│   ├── hotkey.py         # global "call Bro" hotkey
│   ├── ws_client.py      # WebSocket /ws/events → Qt signal
│   ├── api_client.py     # HTTP client to backend (QThread per call)
│   └── panels/           # TODO (M12): usage.py water.py settings.py chat.py
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
Call Arun (tray click / Ctrl+Alt+B) → appears bottom-right, greeting bubble (no AI)
Left-click  → reaction + "Hey <name>! 👋" bubble
Right-click → CommandsPanel: Quick Commands (open/close YouTube/Instagram, usage, water,
              tidy, undo) | Ask Bro (type your own)... | Remind me to drink now | Pause |
              Clear chat | Start at login | Hide Bro | Quit
Nothing for autoHideSeconds → back to the tray
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
  "comparison": "<enum|null>", "folder": "<string|null>", "target": "<string|null>" }
```

| Field | Allowed values |
|---|---|
| `intent` | `usage_query`, `compare_usage`, `top_app`, `screen_time`, `longest_session`, `most_active_hour`, `compare_days`, `water_status`, `log_water`, `last_water_reminder`, `tidy_folder`, `undo_tidy`, `open_site`, `close_site_tab`, `open_app`, `close_app`, `open_settings`, `unknown` |
| `target` | free text ≤ 80 chars, **only** for `open_app` / `close_app` / `open_settings` (an app or Settings-page name). Matched by the backend against what is actually installed / running; never executed blindly |
| `period` | `today`, `yesterday`, `this_week`, `last_week`, `last_7_days`, `this_month` |
| `comparison` | `average`, `yesterday`, `last_week`, `none` |
| `application` | must be in tracked list (config) or `any`; aliases resolved by backend (yt → youtube.com) |
| `folder` | one of known folder keys: `downloads`, `desktop`, `documents`, `pictures`, `videos` (no free paths from the LLM) |

Backend validation (mandatory): enum membership, application in tracked list, folder key in whitelist, required slots per intent. Invalid → clarification, never execute. Required slots: `usage_query` (application; period defaults to `today`), `compare_usage` (application, period; comparison defaults `average`), `top_app`/`screen_time`/`longest_session`/`most_active_hour` (period default `today`), `tidy_folder` (folder), `open_site`/`close_site_tab` (a tracked site, not `any`), `open_app`/`close_app` (target). If the AI returns `open_app`/`close_app` without a target, the user's own sentence becomes the target and the launcher scans it for an installed/running app.

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
  - open: `open|launch|fire up|pull up|bring up|go to` + name → tracked site ⇒ `open_site`, otherwise `open_app` (target taken from the **raw** text so `github.com` / `Notepad++` survive)
  - close: `close|quit|exit|kill|shut (down)` + name → tracked site or the word `tab` ⇒ `close_site_tab`, otherwise `close_app`. A negative lookahead rejects everyday senses (`close to`, `close enough`, `close by`…) — closing is a real action, false positives are not acceptable
  - settings: `settings`, `night light`, `blue light`, or `change|adjust|lower|raise|dim|…` + `wallpaper|brightness|volume|theme|…` ⇒ `open_settings`
- Ambiguity rule: if two intents score equally, or a compare-style phrase is present without a clear app/period, **hand off to AI** (open/close variants are not a tie: the slots decide).
- Keep patterns in `router/rules.py` as data tables so they are easy to extend and unit-test.

## 11. AI module contract

- `backend/services/ai_gateway.py: OllamaGateway.parse_intent(text: str) -> dict | None`
- Ollama request (`POST http://localhost:11434/api/chat`):
  - `model` from config, `stream: false`, **`format` = JSON schema** (`ai/prompts.intent_schema`: every field constrained to its enum/whitelist, free text only in `target`), **`keep_alive` = `ai.keepAlive`** (default `"5m"`),
  - `options`: `temperature: 0`, `num_predict: 120`, `num_ctx: 1024`.
- **Single-flight**: one lock/queue; a second request waits or returns "busy".
- **Timeout** (default 15 s). Measured on the target PC (GPU): ~6 s cold, ~3 s warm with the 0.5B model. On timeout/connection error/invalid JSON → return `None` → backend says "I couldn't understand that, bro. Try a Quick Question."
- Prompt: short system prompt + ~14 few-shot examples; list the allowed enums; "Respond ONLY with JSON; use `unknown` if unsure; never answer the question."
- Prefer adding a rule (§10) over relying on the model for a common phrasing: rules are instant and deterministic; the 0.5B model is good at picking an intent, weak at copying names.
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

## 16b. Unused-app reminder

An app is **unused** while none of its windows is in the foreground. After `idleAppMinutes` (default 30) Bro appears and asks *"You haven't used X for 30 min, bro. Shall I close it?"* [Yes, close it] [Keep it].
- Yes → polite close (§16c). Keep → never ask about that app again while it stays open. Unanswered for 10 min → treated as keep.
- One question at a time, at least 2 min apart; the question is withdrawn if the user switches back to the app or closes it.
- Never while away (idle ≥ `idleThresholdSeconds`), in DND, or paused. Apps in `idleAppIgnore` (default `ollama app.exe` — Bro's AI needs it) are never asked about.
- Backend: `IdleAppService` + `IdleAppLoop` (30 s tick) → WS `idle_app` / `idle_app_cleared`; answer via `POST /apps/idle/answer {key, close}`.

## 16c. Opening and closing things (no admin rights)

- **Open app:** dynamic catalog of installed apps (Start menu: classic + Store apps), cached 10 min, launched via `explorer shell:AppsFolder\<AppID>`. Matching: exact name > whole words > substring > abbreviation (`vs code` → Visual Studio Code) > fuzzy ≥ 0.85 (typos only — `photoshop` must never open `Photos`). Not installed → say so. A domain (`github.com`) opens in the browser.
- **Close app:** running top-level windows (visible, not cloaked, not shell, not Arun) matched by process name, or by title for Store apps (all hosted in `ApplicationFrameHost.exe`). Every window of the best match gets **WM_CLOSE** (= clicking X): the app may still ask to save. **Never force-kill.**
- **Close tab:** `close_site_tab` keeps the §15 safety re-read: Ctrl+W only if the foreground window is a browser showing that site.
- **Settings:** `ms-settings:` deep links (night light, display, bluetooth, wifi, sound, wallpaper, …). Windows offers no public API to toggle Night light — open its page and say so; do not hack the registry.
- **Out of scope (user decision):** toggling Wi-Fi/Bluetooth, connecting to networks, entering passwords, anything needing admin.

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
| `POST /guard/cancel` · `POST /guard/snooze` · `GET /guard/status` | guard cancel, snooze (+5 min), status |
| `POST /pause` · `POST /resume` | manual Do Not Disturb toggle |
| `POST /tidy/propose` `{folder}` · `POST /tidy/confirm` `{proposal_id}` · `POST /tidy/undo` | tidy |
| `GET /settings` · `PUT /settings` | config read/update (validated) |
| `POST /data/clear` | clear history (usage, water, guard, tidy; confirmation required) |
| `POST /system/autostart` `{enabled}` | set autostart at login |
| `POST /apps/idle/answer` `{key, close}` | answer to "shall I close X?" (§16b) |
| `WS /ws/events` | server→client push: `water_due`, `nag`, `countdown_start`, `countdown_tick`, `tab_closed`, `cancelled`, `idle_app`, `idle_app_cleared` |

**Response envelope** (every answer):
```json
{ "text": "You spent 2h 35m on YouTube yesterday, about 1h more than your usual.",
  "animation": "warn", "needs_confirmation": false, "proposal_id": null, "data": {} }
```
`animation` ∈ `idle, walk, smile, wave, warn, angry, happy, water, greeting, thinking, answering, confused, working, success, sleep` (extended character-state system, character spec 2026-10-07 — see CONTEXT.md D17 and `need-to-do.md` §E for the full personality/state spec and reference photo).

## 19. Response templates (v1, no LLM)

Kept in `router/templates.py`, keyed by intent, filled with DB values. Duration formatter: `155 → "2h 35m"`, `45 → "45m"`, `0 → "0m"`. Tone: friendly, short, calls the user "bro" occasionally. Choose animation by result (e.g. above-average usage → `warn`, low usage → `happy`).
Example: `"You spent {dur} on {site} {period_label}, about {diff} {more_less} than your usual daily average."`

## 20. Client (PyQt6) requirements

- Window flags: `FramelessWindowHint | WindowStaysOnTopHint | Tool | WindowDoesNotAcceptFocus`; `WA_TranslucentBackground`; `WA_ShowWithoutActivating`. Also set `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` via ctypes.
- Animation player: loads `assets/stickers/arun/<pose>.png` or numbered frames at `fps` (default 24); caches `QPixmap`s; mirrors horizontally when walking left; scales by **height** (200–260 px) so poses don't shrink. No art yet for a given pose → falls back to a procedural SVG placeholder (`client/placeholder_svg.py`, D17 in CONTEXT.md) per-pose, independently — dropping in `greeting.png` doesn't require also having `thinking.png`. **When the human supplies generated character art (any chat session, not necessarily this one): follow the "AI AGENT" instructions at the top of `need-to-do.md` §E** — it has the exact filename mapping and no-code-change save path.
- **Presence** (`presence` config): `"on_demand"` (default) — hidden in the tray; shown by tray click or the global hotkey (`callHotkey`, RegisterHotKey, no admin) or by attention events (water, nag/countdown, tab closed, unused app); stands still at the bottom-right of the work area; hides after `autoHideSeconds` without interaction, but never while a popup is open or a reply is pending. `"always"` — always visible and wandering across the whole work area.
- Click vs drag distinction. Right-click opens the **CommandsPanel** (§7) — a plain top-level widget with buttons, **not a QMenu**.
- Reactions are temporary: any reaction pose reverts to idle after a few seconds.
- All network calls run off the UI thread (QThread/worker) and return via signals.
- **Qt rules learned the hard way (each was a real bug):**
  - `setContextMenuPolicy(NoContextMenu)` on the character window — the default policy swallows right-clicks before `mousePressEvent`.
  - Interactive dialogs/popups are **unparented** top-level widgets (a parent with WS_EX_NOACTIVATE makes them unfocusable); pass `WindowStaysOnTopHint` in the **constructor**, never `setWindowFlags()` afterwards.
  - `QApplication.setQuitOnLastWindowClosed(False)` — Tool windows don't count, so closing a dialog would quit the app.
  - Never name a signal `event` (shadows `QObject.event`).
  - Keep every QThread **worker** referenced until it finishes, not just the thread — otherwise it is garbage-collected and the call silently never runs.
  - Clamp popup positions to the screen; flip below the anchor when there is no room above.
  - `WA_DeleteOnClose` popups: guard `isVisible()` against already-deleted wrappers.
- Needs an Edit-style paste support in text boxes (standard Qt widgets already do).
- Single-instance lock (mutex/lock file).

## 21. Config (`%APPDATA%\Arun\config.json`)

```json
{
  "userName": "YourName", "character": "arun", "walking": true, "walkFacesRight": true, "fps": 24,
  "presence": "on_demand", "callHotkey": "Ctrl+Alt+B", "autoHideSeconds": 45,
  "idleAppMinutes": 30, "idleAppIgnore": ["ollama app.exe"],
  "backendHost": "127.0.0.1", "backendPort": 8765, "databasePath": "",
  "waterIntervalMinutes": 45, "waterDailyTarget": 8, "waterSnoozeMinutes": 10,
  "distractingSites": ["youtube.com", "instagram.com"],
  "siteMatchers": { "youtube.com": ["YouTube"], "instagram.com": ["Instagram"] },
  "nagAfterMinutes": 15, "closeAfterMinutes": 25, "warningSeconds": 60,
  "nagRepeatSeconds": 120, "breakResetMinutes": 10, "closeMode": "tabs",
  "pollSeconds": 2, "idleThresholdSeconds": 120, "trackAllApps": true, "storeTitles": false,
  "dndApps": ["zoom.exe", "teams.exe", "ms-teams.exe"],
  "demoMode": false,
  "ai": { "enabled": true, "host": "http://localhost:11434", "model": "qwen2.5:0.5b-instruct",
          "timeoutSeconds": 15, "keepAlive": "5m", "logPrompts": false }
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
| Fullscreen / presentation / busy | `shell32.SHQueryUserNotificationState` — busy = 1 not-present, 2 busy, 3 D3D fullscreen, 4 presentation, 6 quiet time, 7 app; **5 = accepts notifications (normal)** |
| Close tab | `user32.keybd_event` (or `SendInput`) Ctrl down, `W`, Ctrl up |
| Non-focus overlay window | `SetWindowLongW` with `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` |
| Start at login | `winreg` → `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` |
| Work area (above taskbar) | Qt `screen.availableGeometry()` |
| Installed apps | PowerShell `Get-StartApps` (Name + AppID, classic and Store apps) |
| Launch an app | `explorer.exe shell:AppsFolder\<AppID>` |
| Running app windows | `user32.EnumWindows` + `IsWindowVisible` + `GetWindow(GW_OWNER)` + `dwmapi.DwmGetWindowAttribute(DWMWA_CLOAKED)` |
| Close an app politely | `user32.PostMessageW(hwnd, WM_CLOSE)` |
| Settings pages | `os.startfile("ms-settings:<page>")` |
| Global hotkey | `user32.RegisterHotKey` on a dedicated thread with its own message loop |
| Tray icon | Qt `QSystemTrayIcon` |

All OS access is wrapped in `backend/os_integration/windows.py` implementing the interface in `base.py`:
`get_foreground_window()`, `get_idle_seconds()`, `is_dnd_active()`, `send_close_tab()`, `set_autostart(bool)`, `list_apps()`, `launch_app(app_id)`, `list_windows()`, `close_window(hwnd)`, `open_uri(uri)`. (The hotkey and tray live in the client.) Nothing requires admin rights.

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
| M15 | Open/close apps, Settings pages (§16c) | live: open + close Calculator from typed text |
| M16 | Unused-app reminder (§16b) | live: question appears, Keep/Yes answered |
| M17 | On-demand presence: tray, hotkey, auto-hide (§20) | live: hidden at start, hotkey toggles, auto-hides |

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

## 26. Dev setup

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt     # unpinned on purpose (user decision)
.venv\Scripts\python -m pytest -q
.venv\Scripts\python run.py                                 # Arun starts hidden in the tray
```
Git ignores `.venv/`, bytecode, `*.log`, build output and personal photos (`.gitignore`). Runtime data (DB, user config, logs) lives in `%APPDATA%\Arun`, never in the repo.

## 27. Coding conventions

- Type hints everywhere; pydantic models for API I/O; no global singletons (use a small `AppContext`).
- Pure functions for period math, formatting, rule matching so they are trivially testable.
- No blocking calls in async handlers; the Ollama call is `async` with timeout.
- Logging via `logging` to a rotating file; never log API keys or full window titles (unless `storeTitles`).
- Each module ≤ ~250 lines; split otherwise.
- Every new service ships with a test file in `tests/`.
