# need-to-do.md: things YOU (the human) must do

The AI writes the code. These are the things only you can do on your Windows 11 PC.
Tick them off as you go, and tell the AI when something is done (it will record it in `CONTEXT.md`).

---

## A. Install the tools

- [ ] **Python 3.11 or 3.12**: `winget install Python.Python.3.12`. Then check `python --version`.
- [ ] **ffmpeg** (for character video → frames): `winget install Gyan.FFmpeg`. Open a new terminal and run `ffmpeg -version`.
- [ ] **Ollama for Windows**: download from https://ollama.com/download, or `winget install Ollama.Ollama`.
- [ ] **Pull the small model** (~400 MB). *Installed on this machine as `qwen2.5:0.5b-instruct` (that exact tag is what the config uses — D14):*
  ```
  ollama pull qwen2.5:0.5b-instruct
  ```
  Optional stronger model (~1 GB) if intent parsing is poor: `ollama pull qwen2.5:1.5b`.
- [ ] **Test Ollama works** (PowerShell):
  ```
  ollama run qwen2.5:0.5b-instruct "Reply with only {\"ok\":true}"
  ```
  Then check the API: `curl http://localhost:11434/api/tags` should list the model.
- [ ] **Docker: not needed.** Skip it.
- [ ] Optional: **Git** (`winget install Git.Git`) and **VS Code**, so you can keep versions of the project.

> Ollama normally starts in the system tray and listens on `localhost:11434`. Arun loads the model only when a typed question needs it, then unloads it (`keep_alive: 0`), so it won't hog RAM.

## B. Project setup

- [ ] Create the folder (e.g. `C:\Projects\arun`) and put `SKILL.md`, `CONTEXT.md` and `need-to-do.md` inside.
- [ ] Open it in Claude Code / OpenCode / another chat and paste the **Resume prompt** from the top of `CONTEXT.md`.
- [ ] Create a virtual environment (once the AI has made `requirements.txt`):
  ```
  python -m venv .venv
  .venv\Scripts\activate
  python -m pip install -r requirements.txt
  ```
  If PowerShell blocks activation: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## C. Connecting Arun to your computer (Windows OS APIs)

Good news: **no API key, no sign-up, no installation** for these. They are built into Windows, and Python calls them through `ctypes` (plus the `psutil` package, installed by `requirements.txt`). The AI writes the code. Your job is to **verify they work on your machine**.

| What Arun needs | Windows API | What you do |
|---|---|---|
| Which window is in front | `GetForegroundWindow` | verify with the test below |
| Its title ("... - YouTube - Google Chrome") | `GetWindowTextW` | verify with the test below |
| Which program owns it (chrome.exe) | `GetWindowThreadProcessId` + `psutil` | verify with the test below |
| Are you away from the PC | `GetLastInputInfo` | nothing, but test idle in M2 |
| Fullscreen / presentation / meeting | `SHQueryUserNotificationState` | test: watch a fullscreen video, it should say "busy" |
| Close the tab | `keybd_event` (Ctrl+W) | test only in demo mode (below) |
| Overlay that never steals focus | `WS_EX_NOACTIVATE` window style | test in M11: click Arun, your browser must keep focus |
| Start at login | registry `HKCU\...\Run` | test in M13 |

**Quick manual test (do this once; it proves the core trick works).** Save as `probe.py`, run `python probe.py`, and within 5 seconds click your browser on a YouTube page:

```python
import ctypes, ctypes.wintypes as wt, time, psutil
time.sleep(5)
u = ctypes.windll.user32
hwnd = u.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
u.GetWindowTextW(hwnd, buf, 512)
pid = wt.DWORD()
u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
print("TITLE:", buf.value)
print("PROCESS:", psutil.Process(pid.value).name())
```

- [ ] You should see a title containing `YouTube` and a process like `chrome.exe` / `msedge.exe`.
- [ ] **Run the built-in probe too** (M2): `python tools\probe_windows.py`. It shows process, title, idle seconds and DND state once a second for 10 s. Watch a fullscreen video during it: `dnd=True` is expected.
- [ ] If the title does **not** contain "YouTube" (some browsers/languages differ), tell the AI the exact title so it can adjust `siteMatchers` in `config.json`.
- [ ] Note: Windows gives **titles, not URLs**. Only the **active tab** is detected. This is a known limit of v1.

**Windows settings to check**

- [ ] Settings → System → Notifications: allow notifications (Arun uses its own popups, but check anyway).
- [ ] Antivirus / SmartScreen may flag the packaged `Arun.exe` because it sends keystrokes (Ctrl+W) and watches windows. If so, allow it, or run from Python during development.
- [ ] First run: if Windows Firewall asks about Python/uvicorn, **allow private network only** (Arun listens on `127.0.0.1`, so nothing leaves your PC).
- [ ] Settings → Privacy & security → Microphone: **not needed** (no voice).

## D. Safe testing of the tab-closer

The guard sends **Ctrl+W** to your browser. Test carefully:

- [ ] Turn on `"demoMode": true` in `%APPDATA%\Arun\config.json` (nag at 10 s, close at 30 s).
- [ ] Open a **new, empty** YouTube tab in a browser window with nothing important in it.
- [ ] Never test with unsaved work in the browser. Arun re-checks that the active window is still that site before closing, but test on a disposable window first.
- [ ] Set `"demoMode": false` again afterwards.

## E. Character artwork (needed for M11)

You can start with no artwork (the AI uses an SVG placeholder matching your described
look — see `client/animation.py` / `_paint_placeholder` and D17 in CONTEXT.md), but for
the real look, generate art from the full character spec below.

> **AI AGENT — read this when the human attaches/pastes generated character image(s)
> in any future chat (this may be a different session than the one that wrote this
> file — trust this block, not your own memory):**
> 1. For each image the human gives you, work out which pose it's for. Ask the human
>    if it's not obvious from their message or the image itself (compare against the
>    13-state list below — IDLE, WALK, GREETING, HAPPY, WATER, WARN, ANGRY, THINKING,
>    ANSWERING, CONFUSED, WORKING, SUCCESS, SLEEP).
> 2. Read the image with the Read tool first (always — never copy a file you haven't
>    looked at), then save it as `assets/stickers/arun/<pose>.png` using the **lowercase
>    animation key** from the "Mapping" list below (e.g. a GREETING image -> `greeting.png`,
>    not `GREETING.png` or `greet.png` — `client/animation.py`'s `resolve_pose_frames`
>    does an exact-match lookup).
> 3. If the human gives only one image (e.g. just a base/idle portrait), save it as
>    `idle.png` only — don't guess at the other 12 poses. `AnimationPlayer` already
>    prefers a real `<pose>.png` over the SVG placeholder per-pose, independently, so
>    partial art is fine: idle shows the real art, every other pose still shows the
>    SVG placeholder until its own image arrives.
> 4. If the human gives a short video/animated clip (e.g. for `walk`), don't try to
>    save it directly — `client/animation.py` expects either `<pose>.png` or a
>    `<pose>/0001.png, 0002.png, ...` frame sequence, and there is no frame-extraction
>    tool yet (`tools/import_character.py` from the original plan was never built,
>    since single static images turned out to be the actual workflow). Tell the human
>    this and ask whether to (a) extract frames with ffmpeg into `<pose>/NNNN.png`
>    yourself if ffmpeg is available, or (b) just use a single representative frame as
>    `<pose>.png` for now.
> 5. No code changes are needed for any of this — `CharacterWindow`/`AnimationPlayer`
>    already load from `assets/stickers/arun/` automatically. After saving, mention
>    it in CONTEXT.md's session log and file inventory (rule 3 in SKILL.md §0), and
>    update the "artwork ready?" open question in CONTEXT.md §9 if all 13 are in.

**Reference photo:** saved at `assets/stickers/arun/reference_photo.webp` (your own
photo, provided 2026-10-07 — use it as the identity reference when generating art;
do not redesign the character's identity independently).

**Full character spec** (paste this — plus the reference photo — into an image
generator that accepts image input, e.g. ChatGPT image generation, Gemini, or
Midjourney with `--cref`):

> Use this photo as the identity reference for the character. The attached photo is
> me. Do not redesign the character's identity independently.
>
> Character: a Windows 11 desktop companion ("Bro"/Arun). Stylized version of the
> person in the photo — NOT photorealistic. Preserve: curly/wavy black hair, facial
> structure, beard and moustache, skin tone, face proportions, hairstyle, casual
> confident appearance. Style: polished 2D stylized illustration / game-character
> style, friendly, slightly mischievous, confident, expressive, playful, recognizable
> even at small desktop sizes. Keep face, hairstyle, clothing, proportions, skin tone,
> art style and accessories identical across every state below.
>
> States to generate (consistent character, same outfit/proportions throughout):
> **IDLE** (relaxed stand, slight smile, friendly eyes) · **WALK** (natural walk
> cycle, arms move slightly, not running) · **GREETING** (click reaction: small
> wave/hand gesture, head tilt, alert friendly smile) · **HAPPY** (bigger smile,
> bright eyes, small celebratory/thumbs-up gesture) · **WATER** (points toward a
> glass/bottle, slightly concerned-but-friendly) · **WARN** (raised eyebrow, serious
> but not threatening, arms crossed or pointing) · **ANGRY** (comedic annoyed face,
> narrowed eyes, crossed arms — stays friendly underneath, never violent/scary) ·
> **THINKING** (hand near chin, head tilt, eyes up/sideways — brief state) ·
> **ANSWERING** (relaxed confident posture, slight nod) · **CONFUSED** (raised
> eyebrow, head tilt, subtle shrug — not stupid-looking) · **WORKING** (focused,
> small motion indicating activity, e.g. during a file-tidy operation) · **SUCCESS**
> (proud smile, thumbs up, small celebration) · **SLEEP** (relaxed, sleepy, eyes
> occasionally closing — quiet/DND state).
>
> Desktop requirements: transparent background (no background at all, PNG alpha),
> full body visible, plain/no scenery, suitable for a small on-screen sprite, not
> photorealistic rendering, consistent identity in every image.

(The full original spec with personality notes, interaction-flow description, and the
golden-rule architecture note is preserved in the project's session history if you need
the complete wording again — the prompt above is the condensed, generation-ready form.)

**Mapping to this project's animation keys** (`client/animation.py` / backend
`animation` field, SKILL §18): `idle`, `walk`, `greeting` (replaces the old `wave` for
click reactions), `happy`, `water`, `warn`, `angry`, `thinking`, `answering`,
`confused`, `working`, `success`, `sleep`. (`smile`/`wave` still exist for backward
compatibility but `greeting` is now what the client uses on click.)

1. Generate a base `idle.png` first (full body, transparent background) using the
   prompt above with the reference photo attached.
2. For each other state, either regenerate with the same reference + a line like
   "same character, WALK state: ..." (consistency prompting), or animate from
   `idle.png` with an image-to-video tool (Kling AI etc.) for `walk`, 3–5 s loopable
   clips, plain/transparent background, static camera, full body visible.
3. Put everything in one folder, e.g. `C:\Users\<you>\Downloads\arun-poses`, named
   after the animation keys above: `idle.png`, `walk.mp4` (or `walk/0001.png...`),
   `greeting.png`, `happy.png`, `water.png`, `warn.png`, `angry.png`, `thinking.png`,
   `answering.png`, `confused.png`, `working.png`, `success.png`, `sleep.png`.
4. When the AI has built `tools/import_character.py`, run:
   ```
   python tools\import_character.py arun C:\Users\<you>\Downloads\arun-poses
   ```
   First run `--find-loop walk.mp4` and trim as it suggests so the walk doesn't "jump".
- [ ] The free tiers have daily limits. Generate images over a few days if needed.

## F. Choices only you can make

Tell the AI your answers so it records them in `CONTEXT.md`:

- [ ] Your **first name** (for the greeting and settings).
- [ ] Which **sites** to watch besides YouTube and Instagram.
- [ ] Which **apps** should silence Arun (Zoom, Teams, Meet in a browser?, games?).
- [ ] Water **interval** (default 45 min) and **daily target** (default 8 glasses).
- [ ] Nag / close times (defaults 15 / 25 min).
- [ ] Which **folders** may be tidied (default list: Downloads, Desktop, Documents, Pictures, Videos).
- [ ] Model: stay on `qwen2.5:0.5b`, or move to `1.5b` if it misreads your questions.

## G. Verification checklist (after the AI says things are built)

- [ ] Arun appears, is transparent, stays on top, and **does not steal focus** when clicked.
- [ ] He walks along the bottom above the taskbar and faces the walking direction.
- [ ] Click → "Hey bro! 👋" + menu appears instantly (no delay, so no AI is involved).
- [ ] Every **Quick Question** answers instantly with real numbers.
- [ ] Typed "how much youtube today" answers instantly (rules). Typed "was I wasting more time on videos than usual yesterday?" works via Ollama, and afterwards the model is unloaded (check with `ollama ps`, which should list nothing after a few seconds).
- [ ] Ollama stopped (right-click tray icon → Quit): typed questions fail politely; everything else still works.
- [ ] Water popup → YES → glass count +1 in the Water panel.
- [ ] Demo mode closes a disposable YouTube tab at 30 s.
- [ ] "Organize my downloads" → counts shown → YES → files sorted → "undo" restores everything.
- [ ] Restart the PC / app: today's usage and water count are still there.

## G2. How to run and test (backend)

**Run the test suite:**
```
python -m pytest -q
```
Expect `259 passed`. (Tests never touch `%APPDATA%\Arun` — each uses a temp DB/config via `tests/conftest.py`.)

**Start the backend standalone:**
```
python run.py --backend-only
```
This logs a line like `API token: <random-string>` — copy it, you need it for every
POST/PUT/DELETE request and for the WebSocket. `GET /health` (and other safe GET
endpoints) need no token. The token is new every launch; there is no way to run
without one (by design — SKILL §18 security).

Check it's up: `curl http://127.0.0.1:8765/health` → `{"status":"ok",...}`.

**Call an authenticated endpoint (PowerShell example):**
```
$TOKEN = "paste-the-token-here"
curl -H "X-Arun-Token: $TOKEN" -X POST http://127.0.0.1:8765/water/drink
```
A request with no `X-Arun-Token` header gets `401`. A request carrying an `Origin`
header (i.e. from a browser page, not a local script) gets `403` — this is
intentional anti-CSRF behaviour, not a bug.

**Browse the live API docs:** open `http://127.0.0.1:8765/docs` in a browser (Swagger UI)
while the backend is running. You can try every endpoint from there, but you'll still
need to paste the token into the "Authorize" field for anything other than GET.

**Postman / manual-test checklist** (what the AI already verified live on 2026-10-07 —
re-run this after any backend change before trusting it):
- [ ] `GET /health` → `ai.available: true` (means Ollama is reachable)
- [ ] `GET /quick-questions` → 11 items
- [ ] `POST /ask/quick` for each of the 11 `question_id`s → 200 + real text
- [ ] `POST /ask {"text": "how much screen time today"}` → instant (rules, no AI)
- [ ] `POST /ask {"text": "is youtube eating my day"}` → takes a few seconds (AI), correct answer
- [ ] `POST /ask {"text": "what is the meaning of life"}` → clarification message
- [ ] `POST /water/drink`, `GET /water/today` → count increments
- [ ] `GET /guard/status`, `POST /pause`, `POST /resume`
- [ ] `GET /usage/summary?period=today`
- [ ] `GET /settings` (no `apiToken` in response), `PUT /settings` with a harmless key
- [ ] `POST /tidy/propose {"folder":"downloads"}` → counts only, **nothing moves**
      (do NOT call `/tidy/confirm` against a real folder unless you're ready for files
      to actually move — test confirm/undo against a disposable folder, or trust
      `pytest tests/test_tidy_service.py`, which already covers it in an isolated temp dir)
- [ ] A request with no token → `401`
- [ ] A request with an `Origin` header → `403`
- [ ] Stop the server (Ctrl+C, or close the terminal)

## H. Later / optional

- [ ] **Browser extension** for exact URLs (fixes the "title only" limit).
- [ ] Package with PyInstaller (M13): `pyinstaller --noconsole --onefile --name Arun run.py`. The AI will tune the spec file.
- [ ] Start at login: the right-click menu toggle (M13), or `Win+R` → `shell:startup` → shortcut to `Arun.exe`.
- [ ] Back up `%APPDATA%\Arun\arun.db` if you care about your history.

---

### If tokens run out mid-project

Open a new chat or tool, give it this folder and paste the **Resume prompt** from `CONTEXT.md`. It will read `SKILL.md` and `CONTEXT.md`, then continue from **NEXT ACTION**. Nothing needs to be re-explained.
