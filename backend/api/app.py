"""FastAPI application factory for the Value Investing API.

The API is additive: it reuses the same services as the CLI and the
Streamlit UI, and it never persists prices. Run locally with::

    uvicorn backend.api.app:app --reload
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import backend
from backend.api.responses import ApiError, fail
from backend.api.routes import (
    alerts,
    company,
    consensus,
    dcf,
    filings,
    financials,
    insights,
    methodologies,
    screener,
    system,
)

DEFAULT_CORS_ORIGINS = "http://localhost:8501"


def _docs_enabled() -> bool:
    """OpenAPI docs are on unless ``API_ENABLE_DOCS`` says otherwise."""
    value = os.environ.get("API_ENABLE_DOCS", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _cors_origins() -> list[str]:
    """Comma-separated ``API_CORS_ORIGINS`` (default: the Streamlit origin)."""
    raw = os.environ.get("API_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> FastAPI:
    """Build the FastAPI app (a factory so tests can create isolated apps)."""
    docs = _docs_enabled()
    app = FastAPI(
        title="Value Investing API",
        description=(
            "Additive REST API for the Value Investing platform "
            "(see docs/api_design.md and roadmap issue #27)."
        ),
        version=backend.__version__,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return fail(exc.status_code, exc.code, exc.message)

    app.include_router(system.router)
    app.include_router(company.router)
    app.include_router(methodologies.router)
    app.include_router(dcf.router)
    app.include_router(alerts.router)
    app.include_router(financials.router)
    app.include_router(filings.router)
    app.include_router(insights.router)
    app.include_router(screener.router)
    app.include_router(consensus.router)
    return app


app = create_app()
