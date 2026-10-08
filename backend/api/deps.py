"""Injectable service accessors shared by the API routes.

Both accessors are FastAPI dependencies so tests can replace them with stubs
via ``app.dependency_overrides`` — no database or Yahoo needed.
"""

from __future__ import annotations

from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.services.price_service import PriceService

_repository: FinancialRepository | None = None
_price_service: PriceService | None = None


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
