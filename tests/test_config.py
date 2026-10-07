"""Tests for backend/config.py: load, merge, validate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.config import (
    ConfigError,
    ensure_user_config,
    load_config,
    save_config,
    validate_config,
)


def test_defaults_load_and_validate():
    cfg = load_config(Path("does-not-exist.json"))
    assert cfg["userName"] == "Arun"
    assert cfg["ai"]["model"] == "qwen2.5:0.5b"
    assert cfg["backendPort"] == 8765


def test_user_override_merges(tmp_path: Path):
    user = tmp_path / "config.json"
    user.write_text(json.dumps({"userName": "Arun", "waterIntervalMinutes": 30}), encoding="utf-8")
    cfg = load_config(user)
    assert cfg["waterIntervalMinutes"] == 30
    assert cfg["pollSeconds"] == 2  # untouched default stays


def test_user_override_merges_nested_ai_section(tmp_path: Path):
    user = tmp_path / "config.json"
    user.write_text(json.dumps({"ai": {"model": "qwen2.5:1.5b"}}), encoding="utf-8")
    cfg = load_config(user)
    assert cfg["ai"]["model"] == "qwen2.5:1.5b"
    assert cfg["ai"]["enabled"] is True  # sibling default preserved


def test_invalid_json_raises(tmp_path: Path):
    user = tmp_path / "config.json"
    user.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(user)


@pytest.mark.parametrize(
    "patch",
    [
        {"waterIntervalMinutes": 0},
        {"waterIntervalMinutes": -5},
        {"waterIntervalMinutes": "45"},
        {"backendPort": 70000},
        {"closeMode": "kill"},
        {"walking": "yes"},
        {"tidyFolders": ["downloads", "hacks"]},
        {"ai": {"enabled": "yes"}},
        {"ai": {"host": "localhost"}},
        {"userName": ""},
        {"siteMatchers": {"youtube.com": "YouTube"}},
    ],
)
def test_invalid_values_rejected(patch: dict):
    cfg = load_config(Path("does-not-exist.json"))
    cfg.update(patch)
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_ensure_user_config_creates_file(tmp_path: Path):
    target = tmp_path / "Arun" / "config.json"
    assert not target.exists()
    ensure_user_config(target)
    assert target.exists()
    created = json.loads(target.read_text(encoding="utf-8"))
    assert created["ai"]["model"] == "qwen2.5:0.5b"


def test_save_config_roundtrip(tmp_path: Path):
    cfg = load_config(Path("does-not-exist.json"))
    cfg["waterDailyTarget"] = 10
    path = save_config(cfg, tmp_path / "config.json")
    assert load_config(path)["waterDailyTarget"] == 10
