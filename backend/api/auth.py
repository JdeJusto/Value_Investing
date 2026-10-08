"""API-key authentication (single user, personal use).

The key lives in the ``API_KEY`` environment variable and travels in the
``X-API-Key`` header. The check is fail-closed: when ``API_KEY`` is not
configured every protected request gets 503, never a silent pass.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header

from backend.api.responses import ApiError


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """FastAPI dependency gating a route behind the API key."""
    expected = os.environ.get("API_KEY", "")
    if not expected:
        raise ApiError(
            503,
            "API_KEY_NOT_CONFIGURED",
            "API_KEY is not configured on the server",
        )
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise ApiError(401, "UNAUTHORIZED", "Missing or invalid X-API-Key header")
