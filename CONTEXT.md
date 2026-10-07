# CONTEXT: Arun live progress & handoff

> **For any AI agent:** read `SKILL.md` (spec) first, then this file. Continue from **NEXT ACTION**.
> **You MUST update this file after every completed unit of work** (a file, a service, a passing test run). Do not wait until the end: the session can end without warning.
> Edit rules: change the Status Board in place, **append** to Session Log (never rewrite old entries), keep File Inventory accurate, always rewrite NEXT ACTION.

---

## 0. Resume prompt (paste this at the start of a new chat / Claude Code / OpenCode)

```
This folder is the "Arun" project. Read SKILL.md, then CONTEXT.md.
Continue from NEXT ACTION in CONTEXT.md. Do not redo anything marked DONE.
After EVERY completed unit of work, update CONTEXT.md (status board, file inventory,
session log, next action). Build in small units with tests. Do not re-explore the
whole repo: use the File Inventory. Ask me only if something is blocking.
```

---

## 1. Project snapshot

- **Name:** Arun (renamed from "Bro"; the character still calls itself/the user "bro"). A Windows 11 desktop companion. Character window + FastAPI backend + SQLite + optional local Ollama for intent parsing.
- **Character:** blue water-droplet mascot (from the Bro guide), procedural animated SVG until Kling-generated art is supplied (D18).
- **Presence:** hidden in the system tray by default; called with tray click / **Ctrl+Alt+B**; pops up by itself for water, doomscroll nags and unused-app questions; auto-hides (D19).
- **Can do on the PC (no admin, D21):** open installed apps / sites / Settings pages, close apps politely, close YouTube/Instagram tabs, ask before closing apps unused for 30 min (D22).
- **No voice. No cloud AI. No GPT/Sarvam keys.** No system-setting changes (no Wi-Fi/Bluetooth toggles, no Wi-Fi passwords).
- **Golden rule:** Ollama understands (intent JSON only). Backend decides. Database knows. UI displays.
- **User OS:** Windows 11. **Language:** Python 3.13 in project venv `.venv` (D26).
- **Constraint:** user has limited tokens. Prefer small, tested units and keep this file current.

## 2. Status board

Legend: `TODO` · `IN PROGRESS` · `DONE` · `BLOCKED`

| # | Milestone | Status | Notes |
|---|---|---|---|
| P | Planning / architecture / spec | **DONE** | `SKILL.md`, `CONTEXT.md`, `need-to-do.md` written |
| M0 | Scaffold, config loader, run.py, logging | **DONE** | `run.py --backend-only` + `/health` verified live (ai.available=true) |
| M1 | DB schema, migrations, repositories | **DONE** | temp DB tests: schema, idempotent migration, 5 repos |
| M2 | Windows OS integration (ctypes) | **DONE (unit-tested; live check pending by human)** | unit-tested with fakes; Arun must run `tools\probe_windows.py` (need-to-do §C) |
| M3 | Activity tracker (sessions) | **DONE (unit-tested; live check pending by human)** | fake-clock tests + live run writes `tracker.heartbeat` to %APPDATA%\Arun\arun.db; live YouTube check pending |
| M4 | Usage + Stats services | **DONE** | period helper + seeded-service tests |
| M5 | Quick Questions API + templates | **DONE** | `/quick-questions` + `/ask/quick` verified live for all 11 IDs |
| M6 | Rule-based router + pending confirmation | **DONE** | rules+validate+pending+`POST /ask` verified live; 52 rules + 16 router tests |
| M7 | AI module (Ollama) + validation | **DONE** | live: `is youtube eating my day` → usage_query → executed; meaning-of-life → `unknown` → clarification; ai_calls logged |
| M8 | Water service + scheduler + events | **DONE** | WaterService (persisted first_due, snooze 10 min) + WaterLoop + WS /ws/events + 3 endpoints verified live |
| M9 | Distraction guard + demo mode | **DONE** | 13 fake-clock tests (streak, nag/repeat, countdown, safety re-check, cancel, DND/idle, demo, snooze); lifespan task wired; live startup ok; Arun: manual demo test (need-to-do §D) |
| M10 | Tidy service + undo | **DONE (unit-tested; live test pending by human)** | propose/confirm/undo in temp dir + router + API tests; live: `/tidy/propose downloads` counted real files read-only, bogus confirm → 400, undo-nothing ok. Confirm/undo against real folders deliberately NOT exercised live (would move the user's real files) — covered by isolated temp-dir unit tests instead |
| M10b | Client endpoints: usage/summary, settings, data/clear, system/autostart | **DONE** | `backend/api/{usage,settings,data,system}.py` wired into `create_app`; `tests/test_client_endpoints.py` (10 tests); live-verified |
| M11 | Client: character window + animation | **DONE (live-verified 2026-10-08)** | droplet character (D18), animated SVG, presence modes (D19), click-vs-drag; see D17–D19 |
| M12 | Client: menu, panels, popups | **PARTIAL** | DONE + live-verified: right-click CommandsPanel (D20), Quick Commands, "Ask Bro" free-text dialog, WS popups (water YES/later, guard nag/countdown banner, unused-app question), speech bubble. TODO: Usage / Settings / Water panels, docked chat panel |
| M13 | Packaging, autostart, single instance | TODO | single instance + autostart registry already work; PyInstaller not started |
| M14 | Enhancements / polish | TODO | |
| M15 | System control: open/close apps, Settings pages | **DONE (live-verified)** | `open_app`/`close_app`/`open_settings` intents, dynamic app catalog, polite WM_CLOSE (D21) |
| M16 | Unused-app reminder | **DONE (live-verified)** | IdleAppService + IdleAppLoop + `POST /apps/idle/answer` (D22) |
| M17 | On-demand presence: tray, hotkey, auto-hide | **DONE (live-verified)** | `client/tray.py`, `client/hotkey.py` (D19) |

## 3. NEXT ACTION

> **State (2026-10-08):** everything through M17 works live; 377 tests, 375 pass (the 2 failures are a date-rollover test bug — §8, fix first).
> Run: `.venv\Scripts\activate` then `python run.py` (Bro starts hidden in the tray; Ctrl+Alt+B calls him).
>
> **Next, in order:**
> 1. Fix the 2 date-dependent tests (`tests/test_water_service.py::test_drank_resets_cadence_and_counts`, `tests/test_client_endpoints.py::test_usage_summary_today`) — they started failing when the clock passed midnight; fixture "today" and service "today" disagree. Inject one clock/today_fn into both.
> 2. M12 remaining: Usage / Water / Settings panels and a docked chat panel (SKILL §20), built as plain top-level widgets like `client/popups.py` (see D20 Qt lessons — no QMenu, no dialogs parented to the character window).
> 3. M13: PyInstaller build (`Arun.exe`), test autostart from the venv.
> 4. Character art: when Kling clips arrive, import per need-to-do.md §E (droplet design, D18).
>
> **Still waiting for human:** need-to-do §C/§D/§G checks (probe_windows, demo-mode tab close, real tidy confirm/undo on a disposable folder).

*(Agent: replace this block every time you finish something.)*

## 4. Decisions log (append only)

| ID | Decision | Reason |
|---|---|---|
| D1 | Name = Arun (not Bro) | user request |
| D2 | No voice features | user request |
| D3 | LLM = Ollama native, no Docker | simpler, lighter, GPU access on Windows |
| D4 | Default model `qwen2.5:0.5b` (~400 MB); upgrade path `qwen2.5:1.5b` | user chose smallest; 0.5B is weak at JSON, so strict validation + `format: json` + few-shot are mandatory |
| D5 | LLM output = intent JSON only; answers via templates from DB data | small models invent numbers; golden rule |
| D6 | Ollama called with `keep_alive: 0`, single-flight lock, timeout 15 s | free RAM after each call; avoid slowdown |
| D7 | Backend in a thread inside `run.py` (also runnable standalone) | easy packaging into one exe |
| D8 | Client = PyQt6 (tkinter fallback) | per-pixel transparency, no jagged edges |
| D9 | Windows only in v1; OS access behind an interface | macOS can be added later |
| D10 | Active-window title matching (no URLs) in v1 | Windows cannot read URLs; browser extension is a future enhancement |
| D11 | Arun's own window ignored by tracker; overlay is non-activating | clicking Arun must not break sessions or steal Ctrl+W focus |
| D12 | Added `backendHost`/`backendPort` (default 127.0.0.1:8765) to config, not in SKILL §21 | client and run.py need a configurable port; nothing hard-coded |
| D13 | `ai_calls.prompt` column + `databasePath` config key (empty = default) added beyond SKILL §12/§21 | §11 requires prompt storage when logPrompts=true; tests must not write %APPDATA% |
| D14 | Default model = `qwen2.5:0.5b-instruct` (not `qwen2.5:0.5b`) | that is the tag actually installed in this machine's Ollama; `qwen2.5:0.5b` → 404. Updated config.default.json, %APPDATA% config, need-to-do.md §A |
| D15 | No `ai/schemas.py`; intent validation lives in `backend/router/intent.py` (dict-based `validate_intent`, not pydantic Intent models) | functionally equivalent, already shipped and tested (M6); recorded here per rule 6 instead of silently diverging from SKILL §5 |
| D16 | Moved `ai/gateway.py` → `backend/services/ai_gateway.py` (2026-10-07 audit) | `OllamaGateway` logs to `ai_calls` via `AiRepo`, which needs DB access; SKILL §3 says `ai/` must have **no DB or file access**. Keeping the DB-touching orchestration in `backend/` and leaving `ai/` as a pure prompts+HTTP wrapper (`ai/prompts.py`, `ai/ollama_client.py`) satisfies the golden-rule boundary literally, not just in spirit. All imports/tests updated; 259/259 still pass |
| D17 | Extended `animation` enum from 8 to 15 values (added `greeting, thinking, answering, confused, working, success, sleep`); character window click now sets `greeting` not `wave`; added an SVG-based placeholder character (`client/placeholder_svg.py`) approximating the user's described look (curly black hair, beard, patterned shirt, dark pants, white sneakers) keyed per pose, replacing the plain-blob placeholder | User supplied a detailed character personality/state spec + their own reference photo (2026-10-07, saved at `assets/stickers/arun/reference_photo.webp`); user explicitly chose "expand to full 13-state system now" + "build the SVG placeholder now" when asked. `VALID_ANIMATIONS` in `backend/config.py`/`client/animation.py` is documentation-only (not enforced by any pydantic model or test), so extending it was low-risk. The full generation-ready prompt (for ChatGPT/Gemini image gen with the photo attached) is in `need-to-do.md` §E |

| D18 | Character = blue **water-droplet "Bro" mascot** (bro-desktop-companion-guide.pdf), procedural animated SVG (`client/placeholder_svg.py`: bounce + arm swing, 8-frame cycle); old human `idle.png` + reference photo moved to `assets/stickers/_old_arun_backup/` (git-ignored, personal) | user: "current character was bad", then "switch to water-droplet" from the guide. Kling video generation is a manual human step (need-to-do §E); procedural SVG is the stand-in |
| D19 | **Presence modes**: `presence: "on_demand"` (default) = hidden in tray, called via tray click / global hotkey `callHotkey` (Ctrl+Alt+B, Win32 RegisterHotKey, no admin), auto-appears for attention events (water_due, nag, countdown, tab_closed, idle_app), stands still at bottom-right, auto-hides after `autoHideSeconds` (45) unless a popup/reply is pending. `presence: "always"` = old always-visible desktop-roaming mode (2D random wander, `client/walk_area.py` roam functions) | user: "should not always roam… only comes when I call, without disturbing the screen" |
| D20 | **Qt lessons (do not regress):** (a) right-click opens `CommandsPanel` (plain QPushButtons) — never QMenu on the character window; window sets `ContextMenuPolicy.NoContextMenu` because the default policy swallows right-clicks before `mousePressEvent`; (b) interactive dialogs/popups are **unparented** top-level widgets (parenting to the WS_EX_NOACTIVATE window makes them unfocusable) and get WindowStaysOnTopHint **in the constructor**, never via `setWindowFlags()` later; (c) `app.setQuitOnLastWindowClosed(False)` — Tool windows don't count, so closing any dialog used to quit the app; (d) never name a QObject signal `event` (shadows `QObject.event`, native crash); (e) `ApiClient` must keep each worker referenced (`_jobs`) — a worker held only by a local was garbage-collected, so **no UI→backend REST call ever ran** before this fix; (f) popups are placed with screen clamping (`popups._place`) — a tall panel above the character rendered at y=-612; (g) reactions use `_react(pose, ms)` which auto-reverts to idle, else the wander/idle gate froze the character forever; (h) WA_DeleteOnClose popups: check with `_alive_visible()` (stale wrappers raise RuntimeError) | each was a real bug found and fixed live on 2026-10-07/08 |
| D21 | **System control = open/close only, no admin rights.** `open_app` (Start-menu catalog via `Get-StartApps`, launch via `explorer shell:AppsFolder\<AppID>`, fuzzy/abbreviation match, domains → browser), `close_app` (WM_CLOSE to every window of the best-matching running app = clicking X; app can still prompt to save; never force-kill), `open_settings` (ms-settings: deep links). Night light has no public API → its Settings page opens and Bro says so. Wi-Fi/Bluetooth toggles and Wi-Fi password connect were built then **removed** | user: "only do the small things… don't give the full permission — just open and close" |
| D22 | **Unused-app reminder**: app counts as unused while none of its windows is foreground; after `idleAppMinutes` (30) Bro asks once "Shall I close X?"; Yes → polite WM_CLOSE; Keep → never ask about it again while it stays open; one question at a time, ≥2 min apart, unanswered 10 min = keep, cleared if the user switches back; never while away/DND/paused; `idleAppIgnore` (default `ollama app.exe`, Bro's AI needs it) | user: "if any app not closed more than 30 min, ask permission, close on yes" |
| D23 | **AI tuning** (supersedes D6 keep_alive): `ai.keepAlive: "5m"` (default + user config) — warm calls ~3 s instead of ~8 s; Ollama **structured outputs** (`format` = JSON schema from `ai/prompts.intent_schema`, fields constrained to enums/whitelists) instead of `format: "json"`; when the model picks `open_app`/`close_app` but drops the name, the gateway passes the user's own sentence as `target` and the launcher scans it for an installed/running app (code, not LLM). Rules were extended for observed LLM misses (kill X, change wallpaper/brightness, blue light) | live measurement: 0.5B model was correct ~1/3 of the time on app commands; after these changes 8/8 live test phrases correct |
| D24 | `POST /ask` declares `response_model=AskResponse` (`backend/router/schemas.py`); the router itself stays dict-based | user asked for a pydantic response format; keeps router pure/testable |
| D25 | Windows `SHQueryUserNotificationState` mapping fixed: `QUNS_ACCEPTS_NOTIFICATIONS = 5`, busy = {1,2,3,4,6,7} (verified against Microsoft docs) | old mapping treated the *normal* state (5) as DND, silently blocking every water reminder and guard nag |
| D26 | Project venv `.venv` (Python 3.13.9); `requirements.txt` without version pins; `.gitignore` added and 29 committed `.pyc` files untracked | user request |

## 5. Interfaces frozen (so agents don't need to re-read code)

*(Fill in as modules are built. Format: signature → one-line behaviour.)*

```
# backend/config.py
#   load_config(user_path: Path|None) -> dict            defaults ⊕ user, validated
#   validate_config(cfg) -> None                          raises ConfigError
#   save_config(cfg, user_path=None) -> Path              validate + write
#   ensure_user_config(path=None) -> Path                 create user file if missing
#   user_config_path() -> Path                            %APPDATA%\Arun\config.json
#   default_user_config_dir() -> Path
#   consts: VALID_ANIMATIONS, VALID_PERIODS, VALID_COMPARISONS, KNOWN_INTENTS, TIDY_FOLDER_KEYS
# backend/logging_setup.py
#   setup_logging(level=INFO, log_path=None) -> Path      rotating %APPDATA%\Arun\logs\arun.log, idempotent
# backend/main.py
#   create_app(config: dict|None) -> FastAPI              app factory; app.state.config
#   GET /health -> {status, version, ai:{enabled, available}}   ai ping cached 30 s, never raises
# run.py
#   main(argv|None) -> int                                --backend-only blocks; else thread + /health wait + client stub
#   wait_for_health(cfg, timeout=20) -> bool
# backend/db/connection.py
#   connect(path=":memory:") -> sqlite3.Connection         Row factory, WAL, FK on
#   Database(path) .execute/.query/.query_one/.transaction()/ .close()   thread-safe, autocommit
#   get_meta(db, key, default=None) / set_meta(db, key, value)
# backend/db/migrations.py
#   migrate(conn) -> int                                  applies pending MIGRATIONS, idempotent
#   current_version(conn) -> int
# backend/db/__init__.py
#   open_db(cfg=None, path=None) -> Database               resolve path (cfg.databasePath or %APPDATA%\Arun\arun.db) + migrate
#   resolve_db_path(cfg=None) -> Path
# backend/db/repositories/usage_repo.py  UsageRepo(db)
#   insert_session(app, start, end, dur, date, website=None, window_title=None) -> id
#   sum_seconds(start_date, end_date, website=None, application=None) -> int
#   daily_totals(start_date, end_date, website=None) -> {date: seconds}  0-filled
#   top_application(...) -> (app, secs)|None · longest_session(...) -> Row|None
#   most_active_hour(...) -> (hour, secs)|None · site_breakdown(...) -> rows
# backend/db/repositories/water_repo.py  WaterRepo(db)
#   add(timestamp, date, type) -> id   (reminder_shown|drank|snoozed|dismissed)
#   count_drunk(date) -> int · last(types=None) -> Row|None · last_of_type(t) · events_on(date)
# backend/db/repositories/tidy_repo.py  TidyRepo(db)
#   create_batch(folder, created_at, confirmed=False) -> id · confirm_batch(id)
#   add_move(batch_id, original, new, moved_at) -> id · moves_of_batch(id) -> rows
#   last_undoable_batch() -> Row|None · mark_undone(batch_id)   (batch + moves)
# backend/db/repositories/guard_repo.py  GuardRepo(db)
#   add_event(timestamp, date, type, site=None) -> id  (nag|countdown_start|tab_closed|cancelled|snoozed)
#   recent(limit=20) · events_on(date) · get_streak()/set_streak(secs, since)  (persisted in meta)
# backend/db/repositories/ai_repo.py  AiRepo(db)
#   log_call(timestamp, intent, latency_ms, success, prompt=None) -> id   prompt only if logPrompts
#   recent(limit=20) · stats() -> {calls, avg_ms, successes}
# backend/os_integration/base.py   OSAdapter(ABC)
#   get_foreground_window() -> {hwnd, pid, process_name, title} | None
#   get_idle_seconds() -> float · is_dnd_active() -> bool · send_close_tab() -> bool
#   set_autostart(enabled: bool) -> None
#   list_apps() -> [{name, app_id}] · launch_app(app_id) -> bool          (D21)
#   list_windows() -> [{hwnd, pid, process_name, title}] (visible, unowned, not cloaked,
#     not shell, not this process) · close_window(hwnd) -> bool  (WM_CLOSE, never kill)
#   open_uri(uri) -> bool   (ms-settings: pages)
# backend/os_integration/helpers.py   (pure)
#   classify(process, title, browsers, site_matchers) -> site|None
#   is_browser · match_site(title, matchers) · is_dnd_app · friendly_app_name
#   process_label('X.exe')->'X' · app_identity(window) -> (key, display)  Store apps keyed by title
#   parse_start_apps_json(text) -> [{name, app_id}]
# backend/os_integration/windows.py  WindowsOSAdapter(dnd_apps)   ctypes/psutil impl
#   list_apps = PowerShell Get-StartApps (~1.2 s, cached by the service) · launch = explorer shell:AppsFolder
#   is_dnd_active uses QUNS busy = {1,2,3,4,6,7}; 5 = accepts notifications (D25)
# backend/os_integration/factory.py  get_os_adapter(config) -> OSAdapter (win32 only)
# tests/fakes.py  FakeOSAdapter(foreground, idle_seconds, dnd) + fg(process, title) helper
# backend/tracker/activity_tracker.py   ActivityTracker(db, os_adapter, config, clock=time.time)
#   tick() -> None            one poll: self-ignore / away-close / gap clamp / midnight split / extend-or-new
#   close() -> None           flush open session at max(clock, last tick)
#   recover() -> called in __init__: closes dangling session from a crashed run (meta)
#   run() -> async loop every pollSeconds (started by main.py lifespan when start_services=True)
#   meta keys: tracker.heartbeat (ISO), tracker.open_session (JSON)
# backend/main.py create_app(config, start_services=True)   lifespan opens DB, starts/stops tracker
# backend/services/periods.py   (pure)
#   period_to_range(period, today=None) -> (start_iso, end_iso)   week = Monday..today
#   days_in_range(a, b) -> int · shift_days(iso, n) -> iso
# backend/services/usage_service.py   UsageService(db, today_fn=date.today)
#   usage(period, site=None, app=None) -> {period, site, app, start, end, seconds}
#   screen_time(period) · top_app(period) · longest_session(period) · most_active_hour(period)
#   (top_app/longest/most_active return dict | None when no rows)
# backend/services/stats_service.py   StatsService(db, today_fn=date.today)
#   compare_days(day_a, day_b, website=None, app=None) -> {a_seconds, b_seconds, diff, more, equal}
#   average_daily(website=None, app=None, days=7) -> float      (excludes today, zero-filled)
#   compare_usage(period, website, app, comparison) -> {..., baseline, diff}   comparison ∈ none|average|yesterday|last_week
# backend/router/templates.py   (pure)
#   fmt_duration(minutes) -> '2h 35m'  (§19 spec unit = MINUTES) · fmt_secs(seconds) -> same
#   fmt_hour(9)->'9 AM' · fmt_clock(iso)->'14:03'
#   render(question_id, data) -> (text, animation)   KeyError if unknown id
# backend/router/quick.py
#   QUICK_QUESTIONS = [ {id,label,category} x11 ]   §8 contract, single source of truth
#   quick_answer(question_id, db, config, today=None) -> envelope dict
#   UnknownQuestion(Exception)
# backend/api/quick.py   GET /quick-questions · POST /ask/quick {question_id}
# backend/router/rules.py   (pure, SKILL §10)
#   normalise(text) -> str · build_aliases(config) -> {alias: site}
#   match_rules(text, config) -> {intent, application, period, comparison, folder[, target]} | None
#   INTENT_TIES resolves exact ties (log>status, screen>usage, reminder>status, compare>usage)
#   open/close ties resolved by slots (_resolve_open_close): tracked site -> open_site/close_site_tab,
#   else open_app/close_app; "settings"/"night light"/"blue light"/change+wallpaper… -> open_settings
#   close verbs guarded by lookahead (not "close to", "close enough"); target read from RAW text
# backend/router/intent.py   (pure, SKILL §9)
#   validate_intent(raw, config) -> dict | None     enums + whitelist + defaults; used for rules AND AI
#   TARGET_INTENTS {open_app, close_app, open_settings}: free-text `target` (≤80 chars), no whitelist
# backend/router/schemas.py   AskResponse(text, animation, needs_confirmation, proposal_id, data)  (D24)
# backend/router/confirmations.py   (SKILL §23)
#   PendingConfirmation(clock=time.time, expiry=120)  .set(payload) .get() (auto-expire) .clear()
# backend/router/router.py
#   QuestionRouter(db, config, ai_gateway=None, pending=None, tidy_service=None, os_adapter=None, clock, today_fn)
#   .ask(text) -> envelope     step1 pending yes/no → step2 rules → step3 AI → execute/clarify
#   .execute(intent) -> envelope   dispatch via _do_<intent> handlers
#   _do_open_site/_do_close_site_tab (foreground safety re-read before Ctrl+W)
#   _do_open_app/_do_close_app (AppLauncherService) · _do_open_settings (SystemService)
#   CLARIFICATION = "I couldn't understand that, bro. Try a Quick Question from my menu."
# backend/api/ask.py   POST /ask {text: 1..500 chars} → QuestionRouter(...).ask(text)
# backend/main.py create_app   app.state.pending = PendingConfirmation(); include ask+quick routers
# ai/prompts.py   (SKILL §11, pure — no DB/file access)
#   system_prompt(config) -> str     enums + tracked sites + target slot + respond-JSON-only rule
#   build_messages(text, cfg) -> [system, user/assistant few-shot x14, user]
#   intent_schema(cfg) -> JSON schema for Ollama structured outputs (D23)
# ai/ollama_client.py   (pure — no DB/file access)   OllamaClient(cfg, post=httpx.post)
#   .chat(messages) -> dict|None     POST /api/chat, format = intent_schema(cfg), keep_alive = ai.keepAlive,
#                                    temp 0/num_predict 120/num_ctx 1024, single-flight lock, never raises
# backend/services/ai_gateway.py   OllamaGateway(db, cfg, client=None)   (D16: moved out of ai/ — needs DB)
#   .parse_intent(text) -> dict|None   enabled check → truncate 300 → chat → validate_intent
#                                      → AiRepo.log_call(latency, success, prompt iff logPrompts)
#   open_app/close_app without target → target = user's text (launcher scans it, D23)
# backend/main.py lifespan   app.state.ai_gateway = OllamaGateway|None (by cfg.ai.enabled)
# backend/api/usage.py   GET /usage/summary?period=   -> UsageService.summary(period)
# backend/api/settings.py   GET /settings · PUT /settings   validated, unknown keys rejected (400),
#   apiToken never returned, restart_required flagged for backendHost/Port/databasePath/pollSeconds
# backend/api/data.py   POST /data/clear {confirm: bool}   wipes usage/water/guard/tidy/ai_calls + meta
# backend/api/system.py   POST /system/autostart {enabled: bool}   -> os_adapter.set_autostart
# tools/ai_eval.py   manual script: runs AI-only phrases through OllamaGateway, prints match report
# client/walk_area.py   (pure)   floor_y · walk_bounds · step (1D, legacy)
#   roam_bounds(l,t,r,b,w,h) · random_target(...) · step_toward(x,y,tx,ty,speed) -> (x,y,facing_right,arrived)
# client/single_instance.py   SingleInstanceLock(path)   .acquire()->bool (reclaims stale/dead-pid locks) · .release()
# client/animation.py   VALID_ANIMATIONS (15 states, D17) · resolve_pose_frames(dir,pose)->[Path] (pure)
#   AnimationPlayer(assets_dir, fps)   .set_pose(pose) · .advance() · .current_pixmap()->QPixmap|None
# client/placeholder_svg.py   (pure)   character_svg(pose, frame=0)->str  water-droplet, bounce/arm-swing
#   cycle of ANIMATION_CYCLE (8) frames (D18)
# client/character_window.py   CharacterWindow(config, api_client=None)   QWidget
#   transparent/always-on-top/non-activating (Qt flags + ctypes WS_EX_NOACTIVATE|WS_EX_TOOLWINDOW),
#   ContextMenuPolicy.NoContextMenu (D20). presence (D19): toggle() · appear(greet) · dismiss() ·
#   _touch() restarts auto-hide · _busy() blocks hiding while popups/reply pending.
#   left click = greeting bubble; right click = CommandsPanel (QUICK_COMMANDS + Ask Bro + actions).
#   _react(pose, ms) shows a reaction then reverts to idle. _ask_text(text) -> POST /ask -> bubble.
#   WS events: water_due, nag, countdown_start/tick, tab_closed, cancelled, idle_app, idle_app_cleared
#   (attention events call appear()). quit_app() closes everything.
# client/popups.py   (unparented top-level widgets, screen-clamped _place)
#   WaterReminderPopup(count,target) .yes/.later · QuestionPopup(text, yes_label, no_label) .yes/.no
#   GuardBanner .show_nag/.show_countdown, .cancel/.snooze · CommandsPanel([(label, callback)])
# client/ws_client.py   EventClient(config) .message(dict) signal, .start()/.stop()   WS /ws/events,
#   own asyncio loop on a QThread, reconnects every 3 s (signal NOT named `event`, D20)
# client/tray.py   BroTray(hotkey_text) .call / .quit_requested signals, .show/.hide/.notify · droplet_icon()
# client/hotkey.py   parse_hotkey('Ctrl+Alt+B') -> (mods, vk)|None · GlobalHotkey(text).pressed, .start()/.stop()
# client/api_client.py   ApiClient(config)   .call(method, path, on_done=, on_error=, **kwargs)
#   HTTP call on its own QThread; (thread, worker) kept in _jobs until done (D20e)
# client/app.py   run_client(config) -> int   single instance, QApplication(quitOnLastWindowClosed=False),
#   CharacterWindow + BroTray + GlobalHotkey; shows window only if presence == "always"
# backend/services/water_service.py   WaterService(db, config, clock=time.time, today_fn=date.today)
#   today_count() -> int · target (cfg waterDailyTarget) · interval_seconds · snooze_seconds
#   next_due() -> float epoch   first run persisted in meta water.first_due (+stale recompute);
#                               snoozed → +waterSnoozeMinutes, drank/reminder/dismissed → +interval
#   due() -> bool · blocked(os_adapter) -> bool (DND or idle ≥ idleThresholdSeconds)
#   drank() -> {count,target} · snooze()/dismiss() -> {.., next_due ISO} · mark_reminder_shown() -> new next_due
#   last_reminder() -> Row|None · today_summary() -> {count,target,next_due ISO}
# backend/scheduler/water_loop.py   WaterLoop(service, notifications, os_adapter=None, tick_seconds=10)
#   await step() -> 'fired'|'blocked'|'not_due'   (fired → WaterRepo reminder_shown + broadcast water_due)
#   await run()   sleep loop, logs exceptions, exits on cancel
# backend/ws/notifications.py   NotificationManager   .connect(ws)/.disconnect(ws)/.client_count
#   await .broadcast(payload) -> sent (drops dead sockets) · .broadcast_soon(payload) fire-and-forget
# backend/api/water.py   POST /water/drink {count,target,animation} · POST /water/snooze {snoozed,next_due}
#   GET /water/today {count,target,next_due}
# backend/api/ws.py   WS /ws/events   registers into app.state.notifications
# backend/main.py create_app   app.state.notifications = NotificationManager(); water+ws routers included
#   lifespan (start_services): WaterLoop task alongside tracker, cancelled on shutdown
# backend/services/guard_service.py   GuardService(db, config, os_adapter, clock=time.time, notifications=None)
#   .tick() -> list[event]     one poll: accrue streak/away, advance machine, emit events
#   .snapshot() -> {state, site, streak_seconds}   for client/debug
#   .snooze(seconds=300) -> {type,site,until}       [5 more min] from countdown popup
#   .run()   async loop every pollSeconds (lifespan task when start_services=True)
#   states IDLE/TRACKING/NAGGING/COUNTDOWN/CLOSING/COOLDOWN; DEMO_TIMINGS when demoMode=true;
#   streak in meta guard.streak_seconds; events in guard_events; safety re-read before Ctrl+W;
#   suppression = DND or idle ≥ idleThresholdSeconds or fg ∈ dndApps; self-pid ignored
#   meta keys: guard.streak_seconds, guard.paused
# backend/api/guard.py
#   GET /guard/status -> {state, site, streak_seconds, seconds_left, paused}
#   POST /guard/cancel -> cancel countdown/nag session
#   POST /guard/snooze -> +5 min snooze (300s cooldown)
#   POST /pause / POST /resume -> manual DND toggle (silences guard + water loop)
# backend/security.py
#   generate_token() -> str                               crypto random per-launch token
#   SecurityMiddleware                                    blocks cross-origin requests; enforces X-Arun-Token on POST/PUT/DELETE
# backend/services/app_launcher_service.py   AppLauncherService(os_adapter=None, clock)   (D21)
#   open_site(site) -> bool · installed_apps() (cached 600 s) · clear_app_cache()
#   open_app(query) -> {status: opened|opened_url|not_found|error, query, name}
#   close_app(query) -> {status: closed|not_running|error, query, name, count}  all windows of best match
#   best_app_match(query, apps) (exact > words > substring > abbreviation 'vscode' > fuzzy ≥0.85)
#   best_app_in_text(sentence, apps) (n-gram scan, no fuzzy) — used when the query is a whole sentence
# backend/services/system_service.py   SETTINGS_PAGES · settings_page(target)->(label, uri)
#   SystemService(os_adapter).open_settings(target) -> {status, page}
# backend/services/idle_app_service.py   IdleAppService(config, os_adapter, is_paused, clock)   (D22)
#   tick() -> events [idle_app{key,name,minutes} | idle_app_cleared{key}] · answer(key, close) -> {text, animation}
# backend/scheduler/idle_app_loop.py   IdleAppLoop(service, notifications, tick_seconds=30) .step()/.run()
# backend/api/apps.py   POST /apps/idle/answer {key, close} -> {text, animation}
# backend/main.py lifespan   app.state.idle_apps + IdleAppLoop task (start_services)
```

## 6. File inventory (keep current: path → purpose → status)

| Path | Purpose | Status |
|---|---|---|
| `SKILL.md` | stable spec | DONE |
| `CONTEXT.md` | this file | DONE (living) |
| `need-to-do.md` | manual tasks for the human | DONE |
| `requirements.txt` | backend + client + ai deps | DONE |
| `config.default.json` | shipped defaults (SKILL §21 + D12) | DONE |
| `run.py` | launcher: backend thread, --backend-only, client stub | DONE |
| `backend/__init__.py` | package marker | DONE |
| `backend/config.py` | load/merge/validate config | DONE |
| `backend/logging_setup.py` | rotating file + console logging | DONE |
| `backend/main.py` | FastAPI factory + `GET /health` | DONE |
| `tests/__init__.py` | package marker | DONE |
| `tests/conftest.py` | fixtures: tmp config, TestClient | DONE |
| `tests/test_config.py` | config load/merge/validate | DONE |
| `tests/test_health.py` | /health behaviour | DONE |
| `backend/db/__init__.py` | open_db + path resolution | DONE |
| `backend/db/schema.sql` | full schema + indexes (SKILL §12) | DONE |
| `backend/db/connection.py` | sqlite connect, Database wrapper, meta helpers | DONE |
| `backend/db/migrations.py` | versioned, idempotent migrations | DONE |
| `backend/db/repositories/usage_repo.py` | sessions write + aggregate reads | DONE |
| `backend/db/repositories/water_repo.py` | water events | DONE |
| `backend/db/repositories/tidy_repo.py` | tidy batches/moves, undo | DONE |
| `backend/db/repositories/guard_repo.py` | guard events + streak in meta | DONE |
| `backend/db/repositories/ai_repo.py` | ai call log + stats | DONE |
| `tests/test_db.py` | schema, migrations, 5 repos | DONE |
| `backend/os_integration/base.py` | OSAdapter ABC | DONE |
| `backend/os_integration/helpers.py` | pure classify/match/DND helpers | DONE |
| `backend/os_integration/windows.py` | ctypes impl (fg, idle, DND, Ctrl+W, autostart) | DONE |
| `backend/os_integration/factory.py` | get_os_adapter | DONE |
| `tests/fakes.py` | FakeOSAdapter + fg() helper | DONE |
| `tests/test_os_integration.py` | helper + fake adapter tests | DONE |
| `tools/probe_windows.py` | manual Windows API check for Arun | DONE |
| `backend/tracker/activity_tracker.py` | session lifecycle, heartbeat, recovery | DONE |
| `backend/tracker/__init__.py` | package marker | DONE |
| `tests/test_tracker.py` | 9 simulated-tick scenarios | DONE |
| `backend/services/__init__.py` | package marker | DONE |
| `backend/services/periods.py` | period → date range (Monday start) | DONE |
| `backend/services/usage_service.py` | usage/top_app/screen_time/longest/hour | DONE |
| `backend/services/stats_service.py` | compare_days/average_daily/compare_usage | DONE |
| `tests/test_periods.py` | period range cases | DONE |
| `tests/test_usage_stats.py` | seeded service numbers | DONE |
| `backend/router/templates.py` | formatters + 11 renderers (text, animation) | DONE |
| `backend/router/quick.py` | catalogue + quick_answer dispatcher | DONE |
| `backend/api/quick.py` | GET /quick-questions, POST /ask/quick | DONE |
| `tests/test_quick_questions.py` | catalogue, 11 IDs, empty-data, formatters | DONE |
| `backend/router/rules.py` | §10 normalise, aliases, pattern scoring, ties | DONE |
| `backend/router/intent.py` | validate_intent: enums, whitelist, defaults | DONE |
| `backend/router/confirmations.py` | pending store, 2-min expiry | DONE |
| `backend/router/router.py` | QuestionRouter: pending → rules → AI → execute | DONE |
| `backend/api/ask.py` | POST /ask | DONE |
| `tests/test_rules.py` | 49-case table + normalise/validate unit tests | DONE |
| `tests/test_router.py` | execute, AI fallback, pending yes/no/expiry, /ask | DONE |
| `ai/__init__.py` | package marker | DONE |
| `ai/prompts.py` | system prompt + 9 few-shot examples (pure, no DB/files) | DONE |
| `ai/ollama_client.py` | Ollama HTTP, single-flight, never raises (pure) | DONE |
| `backend/services/ai_gateway.py` | parse_intent: validate + log to ai_calls (moved from `ai/gateway.py`, D16) | DONE |
| `tests/test_ai_gateway.py` | gateway, client payload/timeout/lock, wiring (14) | DONE |
| `backend/api/usage.py` | GET /usage/summary | DONE |
| `backend/api/settings.py` | GET/PUT /settings | DONE |
| `backend/api/data.py` | POST /data/clear | DONE |
| `backend/api/system.py` | POST /system/autostart | DONE |
| `tests/test_client_endpoints.py` | usage/summary, settings, data/clear, autostart (10) | DONE |
| `tools/ai_eval.py` | manual AI-accuracy eval script (run by hand, not in pytest) | DONE |
| `client/__init__.py` | package marker | DONE |
| `client/walk_area.py` | pure floor/bounds/step math | DONE |
| `client/single_instance.py` | lock-file single-instance guard | DONE |
| `client/animation.py` | pose-frame resolution + AnimationPlayer (15-state enum, D17) | DONE |
| `client/placeholder_svg.py` | procedural animated water-droplet character (D18) | DONE |
| `client/character_window.py` | character window: presence, click/drag, CommandsPanel, reactions, WS event handling | DONE |
| `client/api_client.py` | HTTP calls off the UI thread (QThread; workers kept alive in `_jobs`) | DONE |
| `client/app.py` | run_client(config): single instance + QApplication + tray + hotkey | DONE |
| `client/popups.py` | WaterReminderPopup, QuestionPopup, GuardBanner, CommandsPanel | DONE |
| `client/ws_client.py` | EventClient: WS /ws/events → Qt signal, auto-reconnect | DONE |
| `client/tray.py` | system-tray icon (droplet), Call / Quit | DONE |
| `client/hotkey.py` | global call hotkey (RegisterHotKey thread) | DONE |
| `tests/test_client_walk_area.py` | floor/bounds/step math (8) | DONE |
| `tests/test_client_single_instance.py` | lock acquire/release/stale-reclaim (5) | DONE |
| `tests/test_client_animation.py` | pose-frame resolution (5) | DONE |
| `tests/test_client_placeholder_svg.py` | SVG placeholder generation (5) | DONE |
| `assets/stickers/_old_arun_backup/reference_photo.webp` | user's personal reference photo (moved here, **git-ignored**) | ARCHIVED |
| `backend/services/water_service.py` | drink/snooze/timing, persisted first_due | DONE |
| `backend/scheduler/water_loop.py` | async due-check loop, DND/idle gated | DONE |
| `backend/ws/notifications.py` | NotificationManager broadcast | DONE |
| `backend/api/water.py` | /water/drink, /water/snooze, /water/today | DONE |
| `backend/api/ws.py` | WS /ws/events | DONE |
| `tests/test_water_service.py` | timing, loop, manager, endpoints, WS (14) | DONE |
| `backend/services/guard_service.py` | guard state machine, streak, safety close, demo | DONE |
| `backend/api/guard.py` | /guard/status, /guard/cancel, /guard/snooze, /pause, /resume | DONE |
| `tests/test_guard_service.py` | 18 fake-clock guard scenarios & API tests | DONE |
| `backend/security.py` | SecurityMiddleware, token generator | DONE |
| `tests/test_security.py` | token auth, Origin rejection, WS auth | DONE |
| `assets/stickers/_old_arun_backup/idle.png` | old human-character art, replaced by the droplet (D18); **git-ignored** | ARCHIVED |
| `assets/stickers/arun/` | real character frames go here (`<pose>.png` or `<pose>/0001.png`); empty → droplet SVG | EMPTY |
| `backend/router/schemas.py` | AskResponse pydantic model (D24) | DONE |
| `backend/services/app_launcher_service.py` | open sites/apps, close apps, app matching (D21) | DONE |
| `backend/services/system_service.py` | Settings pages map + open_settings (D21) | DONE |
| `backend/services/idle_app_service.py` | unused-app reminder logic (D22) | DONE |
| `backend/scheduler/idle_app_loop.py` | async loop for the unused-app reminder | DONE |
| `backend/api/apps.py` | POST /apps/idle/answer | DONE |
| `tests/test_app_control.py` | matching, open/close, settings, router + gateway hand-off (≈50) | DONE |
| `tests/test_idle_apps.py` | unused-app reminder service/loop/API (14) | DONE |
| `tests/test_client_hotkey.py` | hotkey parsing (10) | DONE |
| `.gitignore` | ignores bytecode, .venv, logs, build output, personal photos (D26) | DONE |
| `.venv/` | project virtual environment (not in git; recreate from requirements.txt) | LOCAL |

*(Agent: add one row per file you create. Mark `DONE`, `PARTIAL`, or `STUB`.)*

## 7. Test status

| Suite | Result | Last run |
|---|---|---|
| `tests/test_config.py` | 17 passed | 2026-10-07 |
| `tests/test_health.py` | 3 passed (monkeypatched Ollama) | 2026-10-07 |
| `tests/test_db.py` (schema, migrations, repos) | **12 passed**; suite total **32 passed** | 2026-10-07 |
| `tests/test_os_integration.py` (helpers + fakes) | **18 passed**; suite total **50 passed** | 2026-10-07 |
| `tests/test_tracker.py` (simulated ticks) | **9 passed**; suite total **59 passed** | 2026-10-07 |
| `tests/test_periods.py` + `tests/test_usage_stats.py` | **21 passed**; suite total **80 passed** | 2026-10-07 |
| `tests/test_quick_questions.py` | **28 passed**; suite total **108 passed** | 2026-10-07 |
| `tests/test_rules.py` + `tests/test_router.py` | **68 passed**; suite total **176 passed** | 2026-10-07 |
| `tests/test_ai_gateway.py` | **14 passed**; suite total **190 passed** | 2026-10-07 |
| `tests/test_water_service.py` | **14 passed**; suite total **204 passed** | 2026-10-07 |
| `tests/test_guard_service.py` (state machine, fake clock, API) | **18 passed**; suite total **222 passed** | 2026-10-07 |
| `tests/test_tidy_service.py` (propose/confirm/undo/API) | **16 passed**; suite total **238 passed** | 2026-10-07 |
| `tests/test_security.py` (token auth, origin block, WS auth) | **10 passed**; suite total **248 passed** | 2026-10-07 |
| `tests/test_client_endpoints.py` (usage/summary, settings, data/clear, autostart) | **10 passed**; suite total **258 passed** | 2026-10-07 |
| **Full suite, re-verified in self-audit** | **259 passed, 0 failed** (previous "248/248" entry above was stale — M10b's test file existed but had 3 bugs that made it fail/error; see §11 audit entry) | 2026-10-07 |
| `tests/test_client_{walk_area,single_instance,animation,placeholder_svg}.py` (M11) | **23 passed**; suite total **282 passed** | 2026-10-07 |
| **Full suite after M12-partial/M15–M17** (app control, idle apps, hotkey, router/rules additions) | **375 passed, 2 failed** — both failures are the date-rollover test bug (§8), identical with and without this session's changes | 2026-10-08 |

Command: `.venv\Scripts\python -m pytest -q` from project root. Live check: `python run.py --backend-only` → `GET http://127.0.0.1:8765/health` → `{"status":"ok","ai":{"enabled":true,"available":true}}`.

## 8. Known issues / blockers

- `tools\probe_windows.py` and a live YouTube tracking check are not yet verified by the human (need-to-do §C).
- Tidy `confirm`/`undo` were not exercised live against the real Downloads/Desktop/etc. folders during the 2026-10-07 audit (would actually move the user's real files). Logic is covered by `tests/test_tidy_service.py` against isolated temp dirs only. A human should do one real confirm/undo cycle on a disposable folder before trusting it unattended (need-to-do.md §G has a related checklist item).
- **2 tests fail since midnight 2026-10-08** (`test_drank_resets_cadence_and_counts`, `test_usage_summary_today`): fixture data and the service compute "today" differently across the date boundary. Test bug, not app bug — first item in NEXT ACTION.
- AI fallback is a 0.5B model: good at picking the intent, weak at naming the app; mitigated by D23. Upgrade path: `qwen2.5:1.5b`.
- "open notebook" opens **Gemini Notebook** (an installed app with that exact name), not Notepad — by design: exact catalog names win.
- Synthetic clicks (PostMessage/UIA) on Qt buttons were unreliable while the ApiClient bug existed (D20e); since the fix, UI Automation `Invoke` works for live tests (see session 17 method).

## 9. Open questions for the human

1. Final model choice: installed & working = `qwen2.5:0.5b-instruct` (D14). Stay, or try `qwen2.5:1.5b` if intent parsing is poor? (Live check so far: good JSON on usage questions, correctly says `unknown` for "meaning of life".)
2. Which meeting/DND apps should pause Arun? (Default in config: zoom, teams.)
3. Character artwork: the character is now the **water droplet** (D18); the old human `idle.png` is archived. Waiting for Kling-generated droplet clips (idle/walk/water/happy/warn/angry) to import into `assets/stickers/arun/`.
4. Is 45 s the right auto-hide time, and is Ctrl+Alt+B a good call hotkey? (both configurable)

## 10. Ideas / Parked (not in current scope)

- Browser extension for exact URLs; dashboard charts; Pomodoro/focus mode; whitelist/study mode; streaks; 20-20-20 breaks; weekly AI summary (Option B); macOS adapter.

## 11. Session log (append only; newest at the bottom)

| # | Date | What was done | Files touched | Result |
|---|---|---|---|---|
| 0 | 2026-10-07 | Architecture finalised from the Bro guide; wrote the spec, context and manual-tasks files | SKILL.md, CONTEXT.md, need-to-do.md | Planning complete; ready for M0 |
| 1 | 2026-10-07 | M0 done: folder skeleton, requirements, config.default.json, config loader+validator, logging, FastAPI /health, run.py | requirements.txt, config.default.json, run.py, backend/{config,logging_setup,main}.py, tests/{conftest,test_config,test_health}.py | 20/20 tests pass; live `/health` ok (Ollama detected); next = M1 DB layer |
| 2 | 2026-10-07 | M1 done: schema.sql, connection.py (Database wrapper + meta), migrations.py, 5 repositories, open_db wired into app lifespan | backend/db/{__init__,connection,migrations}.py, backend/db/schema.sql, backend/db/repositories/*.py, tests/test_db.py, backend/main.py, backend/config.py, config.default.json, tests/conftest.py | 32/32 tests pass; next = M2 OS integration |
| 3 | 2026-10-07 | M2 done: OSAdapter ABC, pure helpers, Windows ctypes impl (fg/idle/DND/Ctrl+W/autostart), factory, FakeOSAdapter, manual probe script | backend/os_integration/*.py, tests/fakes.py, tests/test_os_integration.py, tools/probe_windows.py, need-to-do.md | 50/50 tests pass; Arun to run probe manually; next = M3 tracker |
| 4 | 2026-10-07 | M3 done: ActivityTracker (tick/close/recover/run), wired into app lifespan (start_services flag), 9 scenario tests | backend/tracker/activity_tracker.py, backend/main.py, tests/test_tracker.py, tests/conftest.py | 59/59 tests pass; live run: heartbeat + schema in real DB; next = M4 usage/stats |
| 5 | 2026-10-07 | M4 done: periods.py (Monday-start ranges), UsageService, StatsService (compare/average), 21 tests | backend/services/{periods,usage_service,stats_service}.py, tests/{test_periods,test_usage_stats}.py | 80/80 tests pass; next = M5 quick questions + templates |
| 6 | 2026-10-07 | M5 done: templates (fmt_duration minutes per §19 + renderers), quick catalogue/dispatch, /ask/quick + /quick-questions, 28 tests | backend/router/{templates,quick}.py, backend/api/quick.py, backend/main.py, tests/test_quick_questions.py | 108/108 tests pass; live endpoints verified; next = M6 rule router |
| 7 | 2026-10-07 | M6 done: rules.py (ties table for ambiguity), intent.py validation, confirmations (2-min expiry), QuestionRouter (pending→rules→AI→execute), POST /ask, 68 tests | backend/router/{rules,intent,confirmations,router}.py, backend/api/ask.py, backend/main.py, tests/{test_rules,test_router}.py | 176/176 tests pass; live /ask verified; next = M7 AI gateway |
| 8 | 2026-10-07 | M7 done: ai/ package (prompts+few-shot, OllamaClient single-flight, Gateway validate+ai_calls log), wired in lifespan, 14 tests; D14 model tag fixed to installed `qwen2.5:0.5b-instruct` (config.default + %APPDATA% + need-to-do) | ai/{prompts,ollama_client,gateway}.py, backend/main.py, config.default.json, tests/{test_ai_gateway,test_config}.py, need-to-do.md | 190/190 tests pass; live E2E: rules→AI→execute + unknown→clarification; next = M8 water |
| 9 | 2026-10-07 | M8 done: WaterService (meta-persisted first_due, snooze/dismiss semantics), WaterLoop step/run, NotificationManager, WS /ws/events, 3 water endpoints, router water handlers refactored onto WaterService, 14 tests | backend/services/water_service.py, backend/scheduler/water_loop.py, backend/ws/*, backend/api/{water,ws}.py, backend/main.py, backend/router/router.py, tests/test_water_service.py | 204/204 tests pass; live endpoints + events rows verified; next = M9 guard |
| 10 | 2026-10-07 | M9 done: GuardService (state machine, streak in meta, nag/repeat, countdown with mandatory safety re-read, cancel, snooze, DND/idle/dndApps suppression, DEMO_TIMINGS, broadcast events, run loop), lifespan task wired next to tracker/water, 13 fake-clock tests | backend/services/guard_service.py, backend/main.py, tests/test_guard_service.py | 217/217 tests pass; live startup ok (/health + tracker heartbeat); Arun: manual demo test per need-to-do §D; next = M10 tidy |
| 11 | 2026-10-07 | API security: per-launch token in X-Arun-Token for POST/PUT/DELETE, ?token for WS, Origin header blocked, test suite fixtures updated | backend/security.py, backend/main.py, run.py, backend/api/ws.py, tests/conftest.py, tests/test_security.py | 243/243 tests pass; next = Step C guard endpoints & manual DND |
| 12 | 2026-10-07 | M9 guard enhanced: GET /guard/status, POST /guard/cancel, POST /guard/snooze (+5m), POST /pause & POST /resume (meta guard.paused, silences guard + water), safety re-read prevents Ctrl+W on Arun window | backend/services/guard_service.py, backend/services/water_service.py, backend/api/guard.py, backend/main.py, tests/test_guard_service.py | 248/248 tests pass; next = Step D tidy service |
| 13 | 2026-10-07 | M10 tidy verified & refined: needs_confirmation flag properly propagated in QuestionRouter._do_tidy_folder; propose/confirm/undo + API endpoints tested with security token | backend/router/router.py, backend/services/tidy_service.py, backend/api/tidy.py, tests/test_tidy_service.py | 248/248 tests pass; next = Step E M10b client endpoints |
| 14 | 2026-10-07 | **Self-audit of prior work** (did not trust CONTEXT.md, verified against code + live run). Found & fixed: (1) CONTEXT.md's "248/248" was stale — real run was 3 failed + 11 errored; root causes were test bugs, not production bugs: `tests/test_router.py`'s `FakeTidy.propose()` mock was missing `needs_confirmation: True` (production `TidyService.propose()` was already correct) so pending-confirmation tests never got a pending state; `tests/test_client_endpoints.py`'s fixture read `app.state.db` before entering the `TestClient` context manager (db is only created in `lifespan`, which starts on context entry) and asserted a nonexistent `fake_adapter.autostart_enabled` attribute (real attr is `.autostart`). (2) `tools/ai_eval.py` did not exist despite being referenced as a required deliverable — created a manual (non-pytest) eval script. (3) Golden-rule violation: `ai/gateway.py` imported `backend.db` and wrote to `ai_calls` via `AiRepo`, contradicting SKILL §3 ("ai/ ... No access to DB or files") — moved to `backend/services/ai_gateway.py` (D16); `ai/` now only holds `prompts.py` + `ollama_client.py`, both DB/file-free. Verified via live run: all 11 quick questions, `/ask` (rules + AI fallback + unknown→clarify), water, guard (status/pause/resume), usage/summary, settings, tidy propose (read-only) + bogus-confirm rejection + undo-nothing, no-token → 401, foreign Origin → 403. Did NOT run a live tidy confirm/undo against real folders (would move the user's actual files) — flagged in §8 Known issues instead. | tests/test_router.py, tests/test_client_endpoints.py, tools/ai_eval.py (new), ai/gateway.py → backend/services/ai_gateway.py (moved), backend/main.py, SKILL.md, CONTEXT.md | **259/259 tests pass**; NEXT ACTION = wait for human verification (need-to-do §C/D/F), then M11 |
| 15 | 2026-10-07 | **M11 built**: `client/` package — walk_area (pure), single_instance lock, AnimationPlayer (real-art-first, SVG-placeholder-fallback), CharacterWindow (transparent/always-on-top/non-activating via Qt flags + ctypes, bottom-of-screen walking, click-vs-drag, right-click menu wired to backend via ApiClient), ApiClient (QThread-based, never blocks UI). User supplied a full character personality/state spec + their own reference photo; extended `animation` enum 8→15 states (D17), replaced blob placeholder with an SVG approximation of the user's look, saved the full art-generation prompt + photo into need-to-do.md §E / assets/. Verified offscreen (`QT_QPA_PLATFORM=offscreen`): all required window flags set correctly, walking moves the window, all 15 poses render without error. Could not visually verify on a real display (no screen access from this session). | client/*.py (new), tests/test_client_*.py (new), backend/config.py, SKILL.md, need-to-do.md, assets/stickers/arun/reference_photo.webp | **282/282 tests pass**; NEXT ACTION = human visual check of `python run.py`, then M12 (menu/panels/popups) |
| 16 | 2026-10-07 | Character artwork: processed user-supplied image with rembg, removed checkerboard background to produce clean transparent alpha `(0,0,0,0)`, saved to `assets/stickers/arun/idle.png` (941x1672 RGBA). `AnimationPlayer` automatically loads it for idle | assets/stickers/arun/idle.png, CONTEXT.md, need-to-do.md | **282/282 tests pass**; NEXT ACTION = waiting for human verification |

| 17 | 2026-10-07→08 | **Long live session with the user (M11 → M17).** Character: cat → water-droplet mascot with animated SVG (D18); old human art archived. Desktop-wide 2D roaming, then presence modes (D19): tray icon + Ctrl+Alt+B hotkey + auto-pop for events + auto-hide. Click → speech bubble; right-click → CommandsPanel with Quick Commands + "Ask Bro" dialog (D20). New intents open_site/close_site_tab (foreground safety re-read; "close to" false-positive fixed), open_app/close_app/open_settings with dynamic app catalog + polite WM_CLOSE (D21; Wi-Fi/Bluetooth/password features built then removed on request). WS client + popups (water, guard banner, unused-app question). Unused-app reminder (D22). AI: keepAlive 5m, structured outputs, sentence fallback, extra rules (D23). /ask pydantic response (D24). **Real bugs fixed:** DND constant mapping blocked all reminders (D25); ApiClient GC'd its workers so no UI→backend call ever ran; context-menu policy swallowed right-clicks; panel rendered off-screen; dialogs unfocusable / quit the app; `event` signal crashed; reactions froze the character; QPixmap.mirrored crash; "open photoshop" opened Photos. venv + unpinned requirements + .gitignore (D26). **Live-verified via real hotkey presses, PostMessage right-clicks and UI Automation** (method: find Bro windows by pid via EnumWindows; right-click with WM_RBUTTONDOWN wParam=MK_RBUTTON; click buttons / fill the Ask Bro dialog via System.Windows.Automation Invoke/ValuePattern): water popup, Quick Command, free-text → LLM → Calculator opened, "kill the calculator" closed it, unused-app question answered, auto-hide | client/*, backend/{config,main}.py, backend/os_integration/*, backend/router/{rules,intent,router,templates,schemas}.py, backend/services/{app_launcher,system,idle_app,ai_gateway}_service.py, backend/scheduler/idle_app_loop.py, backend/api/{ask,apps}.py, ai/{prompts,ollama_client}.py, config.default.json, requirements.txt, .gitignore, tests/* | **375/377** (2 = date-rollover test bug); NEXT ACTION = fix those 2 tests, then M12 panels |

**Entry template:**
`| N | YYYY-MM-DD | <1–2 lines> | <files> | <tests pass/fail, what's next> |`

## 12. Handoff checklist (agent runs this when a session may be ending)

1. Finish or cleanly stub the current file. Never leave a half-written file without marking it `PARTIAL` in the inventory.
2. Update Status Board, File Inventory, Test status.
3. Add a Session Log row.
4. Rewrite **NEXT ACTION** with the exact next file/function to write and any partial state (e.g. "`usage_service.py` has `usage()` done, `top_app()` missing").
5. Record any new decisions or blockers.
