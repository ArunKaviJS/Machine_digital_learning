"""Read-only PC specs + live status for "check my system configuration".

psutil + platform for everything portable; the Windows registry for the CPU
model and one PowerShell CIM query for the GPU (cached — it never changes
while Arun runs). Nothing here changes a setting.
"""

from __future__ import annotations

import os
import platform
import time
from typing import Any, Callable

import psutil

SECTIONS = ("os", "cpu", "memory", "disk", "gpu", "battery")
ALIASES = {"os": ("windows",), "cpu": ("processor",), "memory": ("ram",),
           "disk": ("storage", "drive"), "gpu": ("graphics",)}
_gpu_cache: dict[str, Any] = {"names": None}


def _gb(n: float) -> str:
    return f"{n / 1024 ** 3:.1f}"


def _cpu_name() -> str:
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return " ".join(str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).split())
        except OSError:
            pass
    return platform.processor() or "unknown CPU"


def _gpu_names() -> list[str]:
    if _gpu_cache["names"] is None:
        names: list[str] = []
        if os.name == "nt":
            try:
                from backend.os_integration.windows import _powershell

                out = _powershell("(Get-CimInstance Win32_VideoController).Name", timeout=10)
                names = [line.strip() for line in out.splitlines() if line.strip()]
            except Exception:
                names = []
        _gpu_cache["names"] = names
    return _gpu_cache["names"]


def _os_name() -> str:
    if os.name == "nt":
        build = int(platform.version().split(".")[-1] or 0) if platform.version() else 0
        major = "11" if build >= 22000 else platform.release()
        edition = ""
        try:
            edition = platform.win32_edition() or ""
        except Exception:
            pass
        return f"Windows {major} {edition}".strip() + f" (build {build})"
    return f"{platform.system()} {platform.release()}"


class SystemInfoService:
    def __init__(self, gpu_fn: Callable[[], list[str]] = _gpu_names,
                 clock: Callable[[], float] = time.time):
        self.gpu_fn = gpu_fn
        self.clock = clock

    def section(self, name: str) -> str:
        if name == "os":
            uptime_h = (self.clock() - psutil.boot_time()) / 3600
            return (f"OS: {_os_name()}, PC name {platform.node()}, "
                    f"up {uptime_h:.1f} h")
        if name == "cpu":
            return (f"CPU: {_cpu_name()}, {psutil.cpu_count(logical=False)} cores / "
                    f"{psutil.cpu_count()} threads, "
                    f"{psutil.cpu_percent(interval=0.3):.0f}% used")
        if name == "memory":
            vm = psutil.virtual_memory()
            return f"RAM: {_gb(vm.used)} of {_gb(vm.total)} GB used ({vm.percent:.0f}%)"
        if name == "disk":
            parts = []
            for p in psutil.disk_partitions(all=False):
                if "cdrom" in p.opts or not p.fstype:
                    continue
                try:
                    du = psutil.disk_usage(p.mountpoint)
                except OSError:
                    continue
                parts.append(f"{p.mountpoint.rstrip(chr(92))} {_gb(du.free)} of "
                             f"{_gb(du.total)} GB free")
            return "Disk: " + (", ".join(parts) or "no drives found")
        if name == "gpu":
            names = self.gpu_fn()
            return "GPU: " + (", ".join(names) or "unknown")
        if name == "battery":
            bat = psutil.sensors_battery()
            if bat is None:
                return "Battery: none (desktop PC)"
            plug = "charging" if bat.power_plugged else "on battery"
            return f"Battery: {bat.percent:.0f}%, {plug}"
        raise KeyError(name)

    def report(self, what: str = "all") -> str:
        """One line per section; unknown `what` -> everything."""
        what = (what or "all").strip().lower()
        wanted = [s for s in SECTIONS
                  if s in what or any(a in what for a in ALIASES.get(s, ()))]
        wanted = wanted or list(SECTIONS)
        lines = []
        for name in wanted:
            try:
                lines.append(self.section(name))
            except Exception:
                lines.append(f"{name}: unavailable")
        return " | ".join(lines)
