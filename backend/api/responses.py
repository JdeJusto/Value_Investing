"""Standard response envelope and error body for the API.

Success::

    {"data": ..., "meta": {"source": ..., "as_of": ..., "cache_ttl": ...}}

Error::

    {"error": {"code": ..., "message": ...}}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Exception carrying the standard ``{"error": {...}}`` body.

    Raised by routes and dependencies; converted to a JSON response by the
    handler registered in :func:`backend.api.app.create_app`.
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _as_of() -> str:
    """Current UTC time as ISO 8601 with a trailing ``Z``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ok(data: Any, source: str = "mixed", cache_ttl: int = 300) -> dict[str, Any]:
    """Wrap a payload in the standard ``{data, meta}`` envelope."""
    return {
        "data": data,
        "meta": {
            "source": source,
            "as_of": _as_of(),
            "cache_ttl": cache_ttl,
        },
    }


def fail(status_code: int, code: str, message: str) -> JSONResponse:
    """Build the standard error response."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )
