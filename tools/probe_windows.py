"""Manual probe: run this to verify the Windows APIs Arun needs (need-to-do §C).

    python tools\\probe_windows.py

It prints, every second for ~10 s: foreground window, process, title, idle
seconds, and whether Windows reports a busy/DND notification state.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.os_integration.windows import WindowsOSAdapter  # noqa: E402


def main() -> None:
    adapter = WindowsOSAdapter(dnd_apps=["zoom.exe", "teams.exe", "ms-teams.exe"])
    print("Watching for 10 s - click a YouTube tab, then a fullscreen video...")
    for _ in range(10):
        fg = adapter.get_foreground_window()
        idle = adapter.get_idle_seconds()
        dnd = adapter.is_dnd_active()
        if fg:
            print(f"  process={fg['process_name']!r} title={fg['title']!r} "
                  f"idle={idle:.0f}s dnd={dnd}")
        else:
            print(f"  (no foreground window) idle={idle:.0f}s dnd={dnd}")
        time.sleep(1)
    print("Done. Titles should show 'YouTube'; fullscreen video should show dnd=True.")


if __name__ == "__main__":
    main()
