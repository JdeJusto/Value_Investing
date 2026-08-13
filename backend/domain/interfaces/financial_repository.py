"""Repository interface for persistent normalized financials."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from backend.domain.value_objects.financials_normalized import NormalizedFinancials


class FinancialRepository(ABC):
    """Persistence contract for normalized annual financial data.

    Implementations must be provider-agnostic: they receive and return
    :class:`NormalizedFinancials` objects and know nothing about Yahoo,
    EDGAR or any other data source.
    """

    @abstractmethod
    def upsert(self, financials: NormalizedFinancials) -> None:
        """Insert or update a single fiscal-year record."""

    @abstractmethod
    def upsert_many(self, financials: list[NormalizedFinancials]) -> None:
        """Insert or update a batch of fiscal-year records in one operation."""

    @abstractmethod
    def get_by_year(
        self, ticker: str, fiscal_year: int
    ) -> Optional[NormalizedFinancials]:
        """Return the normalized record for a given fiscal year, if stored."""

    @abstractmethod
    def list_years(self, ticker: str) -> list[NormalizedFinancials]:
        """Return the best record per year for a ticker, most recent first."""

    @abstractmethod
    def list_all(self, ticker: str) -> list[NormalizedFinancials]:
        """Return every stored record (all sources), year desc."""

    @abstractmethod
    def get_best_available(self, ticker: str) -> list[NormalizedFinancials]:
        """Return the most consistent usable history for a ticker.

        Prefers a single source (highest priority and quality, adequate
        coverage); blends per-year best records only when necessary.
        """

    @abstractmethod
    def has_data(self, ticker: str) -> bool:
        """True if at least one record exists for the ticker."""

    @abstractmethod
    def delete_ticker(self, ticker: str) -> None:
        """Remove all records for a ticker."""
