"""Loader contract used by analytics/screener to request data ingestion."""

from __future__ import annotations

from abc import ABC, abstractmethod


class DataLoader(ABC):
    """Fetch → normalize → store cycle for a ticker's financial history.

    Analytics and screening layers depend on this interface so they never
    interact with providers directly; they only ask for data to be
    available and then read it from the repository.
    """

    @abstractmethod
    def load_ticker(
        self, ticker: str, years: int | None = None, force: bool = False
    ) -> None:
        """Ensure normalized historical data exists for the ticker."""
