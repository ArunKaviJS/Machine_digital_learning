"""Load, merge and validate Arun configuration.

Layers (later overrides earlier):
  1. config.default.json  (shipped with the app, project root)
  2. %APPDATA%\\Arun\\config.json  (user overrides, created on first run)

Rule: every configurable value lives here; never hard-code secrets/paths.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.default.json"

VALID_ANIMATIONS = {
    "idle", "walk", "smile", "wave", "warn", "angry", "happy", "water",
    # extended character-state system (character spec, 2026-10-07):
    "greeting", "thinking", "answering", "confused", "working", "success", "sleep",
}
VALID_CLOSE_MODES = {"tabs", "window"}
VALID_PRESENCE = {"on_demand", "always"}
KNOWN_INTENTS = {
    "usage_query", "compare_usage", "top_app", "screen_time", "longest_session",
    "most_active_hour", "compare_days", "water_status", "log_water",
    "last_water_reminder", "tidy_folder", "undo_tidy", "open_site",
    "close_site_tab", "open_app", "close_app", "open_settings", "unknown",
}
VALID_PERIODS = {"today", "yesterday", "this_week", "last_week", "last_7_days", "this_month"}
VALID_COMPARISONS = {"average", "yesterday", "last_week", "none"}
TIDY_FOLDER_KEYS = {"downloads", "desktop", "documents", "pictures", "videos"}


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def default_user_config_dir() -> Path:
    """%APPDATA%\\Arun (falls back to ~/.arun off Windows)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Arun"
    return Path.home() / ".arun"


def user_config_path() -> Path:
    return default_user_config_dir() / "config.json"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be an object: {path}")
    return data


def validate_config(cfg: dict[str, Any]) -> None:
    """Raise ConfigError on any invalid value. Pure function, unit-testable."""
    if not isinstance(cfg.get("userName"), str) or not cfg["userName"].strip():
        raise ConfigError("userName must be a non-empty string")
    if not isinstance(cfg.get("character"), str) or not cfg["character"].strip():
        raise ConfigError("character must be a non-empty string")

    for key in ("backendPort", "fps", "waterIntervalMinutes", "waterDailyTarget",
                "waterSnoozeMinutes", "nagAfterMinutes", "closeAfterMinutes",
                "warningSeconds", "nagRepeatSeconds", "breakResetMinutes",
                "pollSeconds", "idleThresholdSeconds", "maxGapSeconds"):
        value = cfg.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ConfigError(f"{key} must be a positive integer, got {value!r}")

    if not (1 <= cfg["backendPort"] <= 65535):
        raise ConfigError(f"backendPort out of range: {cfg['backendPort']}")
    if not isinstance(cfg.get("databasePath", ""), str):
        raise ConfigError("databasePath must be a string (empty = default location)")
    if cfg["closeMode"] not in VALID_CLOSE_MODES:
        raise ConfigError(f"closeMode must be one of {sorted(VALID_CLOSE_MODES)}")

    if not isinstance(cfg.get("distractingSites"), list) or not all(
        isinstance(s, str) for s in cfg["distractingSites"]
    ):
        raise ConfigError("distractingSites must be a list of strings")
    matchers = cfg.get("siteMatchers")
    if not isinstance(matchers, dict) or not all(
        isinstance(k, str) and isinstance(v, list) and all(isinstance(x, str) for x in v)
        for k, v in matchers.items()
    ):
        raise ConfigError("siteMatchers must map site -> list of title keywords")

    if cfg.get("presence", "on_demand") not in VALID_PRESENCE:
        raise ConfigError(f"presence must be one of {sorted(VALID_PRESENCE)}")
    if not isinstance(cfg.get("callHotkey", ""), str):
        raise ConfigError("callHotkey must be a string like 'Ctrl+Alt+B'")
    for key in ("autoHideSeconds", "idleAppMinutes"):
        value = cfg.get(key, 1)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ConfigError(f"{key} must be a positive integer, got {value!r}")

    for key in ("browsers", "dndApps", "tidyFolders", "idleAppIgnore"):
        value = cfg.get(key)
        if not isinstance(value, list) or not all(isinstance(s, str) for s in value):
            raise ConfigError(f"{key} must be a list of strings")

    unknown_folders = set(cfg.get("tidyFolders", [])) - TIDY_FOLDER_KEYS
    if unknown_folders:
        raise ConfigError(
            f"tidyFolders contains unknown keys {sorted(unknown_folders)}; "
            f"allowed: {sorted(TIDY_FOLDER_KEYS)}"
        )

    for key in ("walking", "walkFacesRight", "trackAllApps", "storeTitles", "demoMode"):
        if not isinstance(cfg.get(key), bool):
            raise ConfigError(f"{key} must be a boolean")

    ai = cfg.get("ai")
    if not isinstance(ai, dict):
        raise ConfigError("ai section must be an object")
    if not isinstance(ai.get("enabled"), bool):
        raise ConfigError("ai.enabled must be a boolean")
    if not isinstance(ai.get("host"), str) or not ai["host"].startswith("http"):
        raise ConfigError("ai.host must be an http(s) URL")
    if not isinstance(ai.get("model"), str) or not ai["model"].strip():
        raise ConfigError("ai.model must be a non-empty string")
    if not isinstance(ai.get("timeoutSeconds"), (int, float)) or ai["timeoutSeconds"] <= 0:
        raise ConfigError("ai.timeoutSeconds must be positive")
    if not isinstance(ai.get("logPrompts"), bool):
        raise ConfigError("ai.logPrompts must be a boolean")


def ensure_user_config(path: Path | None = None) -> Path:
    """Create the user config file from defaults if missing. Returns its path."""
    path = path or user_config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        defaults = _read_json(DEFAULT_CONFIG_PATH)
        path.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
    return path


def load_config(user_path: Path | None = None) -> dict[str, Any]:
    """Load defaults, deep-merge the user file, validate, return the result."""
    defaults = _read_json(DEFAULT_CONFIG_PATH)
    path = user_path or user_config_path()
    user: dict[str, Any] = {}
    if path.exists():
        user = _read_json(path)
    cfg = _deep_merge(defaults, user)
    validate_config(cfg)
    return cfg


def save_config(cfg: dict[str, Any], user_path: Path | None = None) -> Path:
    """Validate then write the user config file."""
    validate_config(cfg)
    path = user_path or user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path
