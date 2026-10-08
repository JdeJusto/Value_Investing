"""System endpoints: health and version (no authentication)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

import backend
from backend.api import API_VERSION
from backend.api.responses import ok

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health")
def health() -> dict[str, Any]:
    """Liveness probe used by the mobile app's "Test connection"."""
    return ok({"status": "ok"}, source="internal", cache_ttl=0)


@router.get("/version")
def version() -> dict[str, Any]:
    """API and application versions (client compatibility checks)."""
    return ok(
        {"api_version": API_VERSION, "app_version": backend.__version__},
        source="internal",
        cache_ttl=0,
    )
