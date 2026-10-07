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

- **Name:** Arun (renamed from "Bro"). A Windows 11 desktop companion. Character window + FastAPI backend + SQLite + optional local Ollama for intent parsing.
- **No voice. No cloud AI. No GPT/Sarvam keys.**
- **Golden rule:** Ollama understands (intent JSON only). Backend decides. Database knows. UI displays.
- **User OS:** Windows 11. **Language:** Python 3.11+.
- **Constraint:** user has limited tokens. Prefer small, tested units and keep this file current.

## 2. Status board

Legend: `TODO` · `IN PROGRESS` · `DONE` · `BLOCKED`

| # | Milestone | Status | Notes |
|---|---|---|---|
| P | Planning / architecture / spec | **DONE** | `SKILL.md`, `CONTEXT.md`, `need-to-do.md` written |
| M0 | Scaffold, config loader, run.py, logging | **DONE** | `run.py --backend-only` + `/health` verified live (ai.available=true) |
| M1 | DB schema, migrations, repositories | **DONE** | temp DB tests: schema, idempotent migration, 5 repos |
| M2 | Windows OS integration (ctypes) | **DONE** | unit-tested with fakes; Arun must run `tools\probe_windows.py` (need-to-do §C) |
| M3 | Activity tracker (sessions) | TODO | |
| M4 | Usage + Stats services | TODO | |
| M5 | Quick Questions API + templates | TODO | |
| M6 | Rule-based router + pending confirmation | TODO | |
| M7 | AI module (Ollama) + validation | TODO | needs Ollama installed, see need-to-do.md §A |
| M8 | Water service + scheduler + events | TODO | |
| M9 | Distraction guard + demo mode | TODO | |
| M10 | Tidy service + undo | TODO | |
| M11 | Client: character window + animation | TODO | needs character assets, see need-to-do.md §E |
| M12 | Client: menu, panels, popups | TODO | |
| M13 | Packaging, autostart, single instance | TODO | |
| M14 | Enhancements / polish | TODO | |

## 3. NEXT ACTION

> **Start M3 (activity tracker).** Create `backend/tracker/activity_tracker.py`: `ActivityTracker(db, os_adapter, config, clock=time.time)` with `tick()` — implements SKILL §14: skip ticks where the foreground process is Arun itself, close session when idle ≥ `idleThresholdSeconds`, classify website via `helpers.classify`, extend/close sessions on (application, website) change, clamp gaps > `maxGapSeconds`, split sessions at midnight, flush on `close()`; writes rows via `UsageRepo.insert_session` and a `meta['heartbeat']` heartbeat. `run()` loop = asyncio task every `pollSeconds` (started from main.py lifespan later — for now expose `tick()` + `run_once()` style API so tests drive it). Tests: `tests/test_tracker.py` with `FakeOSAdapter` + fake clock: idle closes session, site change opens new row, midnight split, Arun-window ignored, gap clamped. Then update CONTEXT.md and proceed to M4.

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
# backend/os_integration/helpers.py   (pure)
#   classify(process, title, browsers, site_matchers) -> site|None
#   is_browser · match_site(title, matchers) · is_dnd_app · friendly_app_name
# backend/os_integration/windows.py  WindowsOSAdapter(dnd_apps)   ctypes/psutil impl
# backend/os_integration/factory.py  get_os_adapter(config) -> OSAdapter (win32 only)
# tests/fakes.py  FakeOSAdapter(foreground, idle_seconds, dnd) + fg(process, title) helper
# ai/gateway.py              (planned) parse_intent(text) -> Intent | None
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
| `backend/api/`, `services/`, `router/`, `tracker/`, `scheduler/`, `db/`, `os_integration/`, `ai/`, `client/`, `assets/stickers/arun/`, `tools/` | folder skeleton | DONE (empty) |

*(Agent: add one row per file you create. Mark `DONE`, `PARTIAL`, or `STUB`.)*

## 7. Test status

| Suite | Result | Last run |
|---|---|---|
| `tests/test_config.py` | 14 passed | 2026-10-07 |
| `tests/test_health.py` | 3 passed (monkeypatched Ollama) | 2026-10-07 |
| `tests/test_config.py` parametrised + roundtrip (total suite) | **20 passed** | 2026-10-07 |
| `tests/test_db.py` (schema, migrations, repos) | **12 passed**; suite total **32 passed** | 2026-10-07 |
| `tests/test_os_integration.py` (helpers + fakes) | **18 passed**; suite total **50 passed** | 2026-10-07 |

Command: `pytest -q` from project root. Live check: `python run.py --backend-only` → `GET http://127.0.0.1:8765/health` → `{"status":"ok","ai":{"enabled":true,"available":true}}`.

## 8. Known issues / blockers

- None yet.

## 9. Open questions for the human

1. Final model choice: stay on `qwen2.5:0.5b` or start with `qwen2.5:1.5b`? (Default: 0.5b, and swap if intent parsing is poor.)
2. Which meeting/DND apps should pause Arun? (Default in config: zoom, teams.)
3. Character artwork: is it ready (see need-to-do.md §E)? If not, M11 uses placeholder shapes.

## 10. Ideas / Parked (not in current scope)

- Browser extension for exact URLs; dashboard charts; Pomodoro/focus mode; whitelist/study mode; streaks; 20-20-20 breaks; weekly AI summary (Option B); macOS adapter.

## 11. Session log (append only; newest at the bottom)

| # | Date | What was done | Files touched | Result |
|---|---|---|---|---|
| 0 | 2026-10-07 | Architecture finalised from the Bro guide; wrote the spec, context and manual-tasks files | SKILL.md, CONTEXT.md, need-to-do.md | Planning complete; ready for M0 |
| 1 | 2026-10-07 | M0 done: folder skeleton, requirements, config.default.json, config loader+validator, logging, FastAPI /health, run.py | requirements.txt, config.default.json, run.py, backend/{config,logging_setup,main}.py, tests/{conftest,test_config,test_health}.py | 20/20 tests pass; live `/health` ok (Ollama detected); next = M1 DB layer |
| 2 | 2026-10-07 | M1 done: schema.sql, connection.py (Database wrapper + meta), migrations.py, 5 repositories, open_db wired into app lifespan | backend/db/{__init__,connection,migrations}.py, backend/db/schema.sql, backend/db/repositories/*.py, tests/test_db.py, backend/main.py, backend/config.py, config.default.json, tests/conftest.py | 32/32 tests pass; next = M2 OS integration |
| 3 | 2026-10-07 | M2 done: OSAdapter ABC, pure helpers, Windows ctypes impl (fg/idle/DND/Ctrl+W/autostart), factory, FakeOSAdapter, manual probe script | backend/os_integration/*.py, tests/fakes.py, tests/test_os_integration.py, tools/probe_windows.py, need-to-do.md | 50/50 tests pass; Arun to run probe manually; next = M3 tracker |

**Entry template:**
`| N | YYYY-MM-DD | <1–2 lines> | <files> | <tests pass/fail, what's next> |`

## 12. Handoff checklist (agent runs this when a session may be ending)

1. Finish or cleanly stub the current file. Never leave a half-written file without marking it `PARTIAL` in the inventory.
2. Update Status Board, File Inventory, Test status.
3. Add a Session Log row.
4. Rewrite **NEXT ACTION** with the exact next file/function to write and any partial state (e.g. "`usage_service.py` has `usage()` done, `top_app()` missing").
5. Record any new decisions or blockers.
