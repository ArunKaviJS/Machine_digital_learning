"""Settings endpoints (SKILL §18): GET /settings, PUT /settings."""

from __future__ import annotations

import copy
from typing import Any
from fastapi import APIRouter, HTTPException, Request

from backend.config import ConfigError, _deep_merge, save_config, user_config_path, validate_config

router = APIRouter()

ALLOWED_TOP_LEVEL_KEYS = {
    "userName", "character", "walking", "walkFacesRight", "fps",
    "backendHost", "backendPort", "databasePath",
    "waterIntervalMinutes", "waterDailyTarget", "waterSnoozeMinutes",
    "distractingSites", "siteMatchers", "nagAfterMinutes", "closeAfterMinutes",
    "warningSeconds", "nagRepeatSeconds", "breakResetMinutes", "closeMode",
    "pollSeconds", "idleThresholdSeconds", "maxGapSeconds", "trackAllApps",
    "storeTitles", "browsers", "dndApps", "tidyFolders", "demoMode", "ai",
    "tidyCategories",
}
ALLOWED_AI_KEYS = {
    "enabled", "host", "model", "timeoutSeconds", "keepAlive", "logPrompts"
}
RESTART_KEYS = {"backendHost", "backendPort", "databasePath", "pollSeconds"}


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    """Get current configuration (excluding internal keys)."""
    cfg = request.app.state.config
    return {k: v for k, v in cfg.items() if k != "apiToken"}


@router.put("/settings")
def update_settings(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """Validate and save configuration updates. Reject unknown keys."""
    # 1. Reject unknown keys
    unknown_top = set(body.keys()) - ALLOWED_TOP_LEVEL_KEYS
    if unknown_top:
        raise HTTPException(400, f"Unknown configuration key(s): {sorted(unknown_top)}")

    if "ai" in body:
        if not isinstance(body["ai"], dict):
            raise HTTPException(400, "ai section must be an object")
        unknown_ai = set(body["ai"].keys()) - ALLOWED_AI_KEYS
        if unknown_ai:
            raise HTTPException(400, f"Unknown ai key(s): {sorted(unknown_ai)}")

    # 2. Merge and validate
    current_cfg = copy.deepcopy(request.app.state.config)
    api_token = current_cfg.get("apiToken")
    merged = _deep_merge(current_cfg, body)
    if api_token is not None:
        merged["apiToken"] = api_token

    try:
        validate_config(merged)
    except ConfigError as exc:
        raise HTTPException(422, str(exc)) from exc

    # 3. Check if restart required
    restart_required = any(current_cfg.get(k) != merged.get(k) for k in RESTART_KEYS)

    # 4. Save to user config file
    user_path = getattr(request.app.state, "user_config_path", None) or user_config_path()
    try:
        save_config(merged, user_path=user_path)
    except Exception as exc:
        raise HTTPException(500, f"Failed to save configuration: {exc}") from exc

    request.app.state.config = merged
    return {
        "settings": {k: v for k, v in merged.items() if k != "apiToken"},
        "restart_required": restart_required,
    }
