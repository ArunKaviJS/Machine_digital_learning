"""Rotating-file + console logging for Arun.

Log files live in %APPDATA%\\Arun\\logs\\arun.log (5 x 1 MB).
Never log API keys or full window titles (unless storeTitles).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.config import default_user_config_dir

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_CONFIGURED = False


class SafeRotatingFileHandler(RotatingFileHandler):
    """Windows can't rename a log file another process has open (a second
    Arun / backend-only run): RotatingFileHandler then printed a
    PermissionError traceback for EVERY log line. Skip that rotation and
    keep logging; the next rollover tries again."""

    def doRollover(self) -> None:  # noqa: N802 (logging API)
        try:
            super().doRollover()
        except PermissionError:
            if self.stream is None:
                self.stream = self._open()
            self.maxBytes *= 2  # don't retry on every single line


def log_dir() -> Path:
    return default_user_config_dir() / "logs"


def setup_logging(level: int = logging.INFO, log_path: Path | None = None) -> Path:
    """Configure root logger once; safe to call repeatedly. Returns log file path."""
    global _CONFIGURED
    path = log_path or (log_dir() / "arun.log")
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if _CONFIGURED:
        return path
    root.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = SafeRotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _CONFIGURED = True
    return path
