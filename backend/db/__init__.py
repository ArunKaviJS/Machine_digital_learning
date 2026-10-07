"""DB open helper: resolves path from config, applies migrations, returns Database."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.config import default_user_config_dir
from backend.db.connection import Database, get_meta, set_meta
from backend.db.migrations import migrate


def resolve_db_path(cfg: dict[str, Any] | None = None) -> Path:
    custom = (cfg or {}).get("databasePath") or ""
    if custom:
        return Path(custom)
    return default_user_config_dir() / "arun.db"


def open_db(cfg: dict[str, Any] | None = None, path: str | Path | None = None) -> Database:
    """Open (creating if needed) the app database and run migrations."""
    db = Database(path if path is not None else resolve_db_path(cfg))
    migrate(db.raw)
    return db


__all__ = ["Database", "open_db", "resolve_db_path", "get_meta", "set_meta", "migrate"]
