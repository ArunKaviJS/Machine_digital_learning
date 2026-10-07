# need-to-do.md: things YOU (the human) must do

The AI writes the code. These are the things only you can do on your Windows 11 PC.
Tick them off as you go, and tell the AI when something is done (it will record it in `CONTEXT.md`).

---

## A. Install the tools

- [ ] **Python 3.11 or 3.12**: `winget install Python.Python.3.12`. Then check `python --version`.
- [ ] **ffmpeg** (for character video → frames): `winget install Gyan.FFmpeg`. Open a new terminal and run `ffmpeg -version`.
- [ ] **Ollama for Windows**: download from https://ollama.com/download, or `winget install Ollama.Ollama`.
- [ ] **Pull the small model** (~400 MB):
  ```
  ollama pull qwen2.5:0.5b
  ```
  Optional stronger model (~1 GB) if intent parsing is poor: `ollama pull qwen2.5:1.5b`.
- [ ] **Test Ollama works** (PowerShell):
  ```
  ollama run qwen2.5:0.5b "Reply with only {\"ok\":true}"
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

You can start with no artwork (the AI will use a placeholder shape), but for the real look:

1. **Base image** (ChatGPT image generation or Gemini, free tier is fine). Prompt (edit the bracket parts):
   > 3D Pixar-style animated character of [describe Arun, e.g. a friendly guy with messy hair and a short beard], full body, standing facing the camera, friendly smile, hands in pockets, wearing [outfit]. Plain solid white background, soft studio lighting, entire body visible including shoes.

   Save as `idle.png`.
2. **Animations** (Kling AI or similar image-to-video, start image = `idle.png`). Use short 3–5 s clips, plain white background, static camera, full body visible:
   - `walk.mp4`: turns to the side and walks in place facing right, relaxed walk cycle, loopable.
   - `water.mp4`: pulls out a water bottle and offers it to the viewer, holds the pose.
   - `happy`: laughs, thumbs up. `warn`: crosses arms, raises an eyebrow, shakes head. `angry`: frowns, points at the camera.
   - **New for Arun (not in the original guide):** `smile` (small friendly smile) and `wave` (waves hello). Until you make them, the AI can reuse `happy` and `idle`.
3. Put everything in one folder, e.g. `C:\Users\<you>\Downloads\arun-poses` (names: `idle.png`, `walk.mp4`, `water.mp4`, `happy.mp4`, `warn.png`, `angry.png`, ...).
4. When the AI has built `tools/import_character.py`, run:
   ```
   python tools\import_character.py arun C:\Users\<you>\Downloads\arun-poses
   ```
   First run `--find-loop walk.mp4` and trim as it suggests so the walk doesn't "jump".
- [ ] The free tiers have daily limits. Generate clips over a few days if needed.

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

## H. Later / optional

- [ ] **Browser extension** for exact URLs (fixes the "title only" limit).
- [ ] Package with PyInstaller (M13): `pyinstaller --noconsole --onefile --name Arun run.py`. The AI will tune the spec file.
- [ ] Start at login: the right-click menu toggle (M13), or `Win+R` → `shell:startup` → shortcut to `Arun.exe`.
- [ ] Back up `%APPDATA%\Arun\arun.db` if you care about your history.

---

### If tokens run out mid-project

Open a new chat or tool, give it this folder and paste the **Resume prompt** from `CONTEXT.md`. It will read `SKILL.md` and `CONTEXT.md`, then continue from **NEXT ACTION**. Nothing needs to be re-explained.
