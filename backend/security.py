"""Security middleware and token helpers for Arun backend (SKILL §18).

Rules:
1. Every data-mutating HTTP method (POST, PUT, DELETE, PATCH) requires the
   'X-Arun-Token' header matching the per-launch token. Missing -> 401, Invalid -> 403.
2. GET /health (and other safe GET endpoints) stay open.
3. CORS: Arun is a local desktop companion, not a web app. Requests bearing an
   'Origin' header from a web origin are rejected with 403.
4. WebSocket /ws/events requires the token as query parameter ?token=...
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("arun.security")

TOKEN_HEADER = "x-arun-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def generate_token() -> str:
    """Generate a random cryptographically secure token for the launch."""
    return secrets.token_urlsafe(32)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Reject requests with a web Origin header (anti-CORS / CSRF)
        origin = request.headers.get("origin")
        if origin is not None and origin.strip():
            logger.warning("Rejected cross-origin request from origin=%s", origin)
            return JSONResponse(
                {"detail": "Cross-origin requests are forbidden."},
                status_code=403,
            )

        # 2. Check token on state-changing methods
        if request.method not in SAFE_METHODS:
            token = request.headers.get(TOKEN_HEADER)
            expected = getattr(request.app.state, "api_token", None)
            if not token:
                return JSONResponse(
                    {"detail": "Missing X-Arun-Token header."},
                    status_code=401,
                )
            if not expected or not secrets.compare_digest(token, expected):
                return JSONResponse(
                    {"detail": "Invalid X-Arun-Token."},
                    status_code=403,
                )

        return await call_next(request)
