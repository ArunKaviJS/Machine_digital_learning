"""Shared pytest fixtures: temp config, test client, no real network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import DEFAULT_CONFIG_PATH, load_config
from backend.main import create_app


@pytest.fixture()
def defaults() -> dict:
    return json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def tmp_config(tmp_path: Path, defaults: dict) -> Path:
    """A user config file in a temp dir (so tests never touch %APPDATA%)."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps(defaults), encoding="utf-8")
    return path


@pytest.fixture()
def cfg(tmp_config: Path, tmp_path: Path) -> dict:
    config = load_config(tmp_config)
    config["databasePath"] = str(tmp_path / "arun.db")  # never touch %APPDATA% in tests
    return config


@pytest.fixture()
def client(cfg: dict) -> TestClient:
    app = create_app(cfg, start_services=False)  # no tracker/OS calls in API tests
    with TestClient(app, headers={"X-Arun-Token": app.state.api_token}) as c:
        c.app.state.ai_gateway = None  # API tests must never hit real Ollama
        yield c
