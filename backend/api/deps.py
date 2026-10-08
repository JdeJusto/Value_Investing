"""Injectable service accessors shared by the API routes.

Both accessors are FastAPI dependencies so tests can replace them with stubs
via ``app.dependency_overrides`` — no database or Yahoo needed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.api.responses import ApiError
from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.services.price_service import PriceService

_repository: FinancialRepository | None = None
_price_service: PriceService | None = None
_portfolio_service: Any = None


def load_company_rows(repository: FinancialRepository, ticker: str) -> list[Any]:
    """Newest-first rows for ``ticker``, or the standard API error.

    Raises :class:`ApiError` 404 ``TICKER_NOT_FOUND`` when the company is
    unknown, and 503 ``SERVICE_UNAVAILABLE`` when the repository itself fails
    (a DB failure must never leak as a 500).
    """
    try:
        rows = [
            row
            for row in (repository.get_best_available(ticker) or [])
            if row is not None
        ]
    except Exception as exc:  # a DB failure is a 503, not a 500
        raise ApiError(
            503, "SERVICE_UNAVAILABLE", "Financial database is unavailable"
        ) from exc
    if not rows:
        raise ApiError(404, "TICKER_NOT_FOUND", f"Unknown ticker: {ticker}")
    return rows


def get_repository() -> FinancialRepository:
    """Financial repository (Financial-DataBase when available).

    Built lazily and shared process-wide; ``build_financial_repository``
    already falls back to the JSON repository when FDB is unreachable.
    """
    global _repository
    if _repository is None:
        from backend.app.cli import build_financial_repository

        _repository = build_financial_repository()
    return _repository


def get_price_service() -> PriceService:
    """Shared ``PriceService`` (in-memory cache; prices are never persisted)."""
    global _price_service
    if _price_service is None:
        _price_service = PriceService()
    return _price_service


def get_portfolio_service() -> Any:
    """Portfolio service, built exactly like the CLI's.

    Every write path goes through :class:`PortfolioService`, which serializes
    read-modify-write blocks with an exclusive ``fcntl.flock``.
    """
    global _portfolio_service
    if _portfolio_service is None:
        from backend.app.cli import build_portfolio_service

        _portfolio_service = build_portfolio_service()
    return _portfolio_service


def get_screener_source() -> Callable[[list[str], Any], list[dict]]:
    """The expensive screener pipeline (screen + enrich).

    Returned as a dependency so tests can replace the Yahoo/DB-bound pipeline
    with a stub via ``app.dependency_overrides``.
    """
    from backend.api.screener_source import load_enriched_universe

    return load_enriched_universe


def get_consensus_service() -> Any:
    """Consensus loader for the API.

    Staleness is *reported* (``meta.warning``) rather than enforced, so a
    slightly old snapshot stays visible instead of turning into a 503.
    """
    from backend.services.consensus_service import ConsensusService

    return ConsensusService(max_age_days=None)
