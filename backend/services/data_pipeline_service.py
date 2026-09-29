"""Data pipeline: fetch raw financials → normalize → persist.

Orchestrates providers, normalizers and the repository while remaining
agnostic to provider internals. Providers only know how to fetch raw
statements; normalizers only know how to translate one provider's format;
the repository only knows how to store canonical data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from collections.abc import Callable

from backend.domain.interfaces.data_loader import DataLoader
from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.interfaces.provider import FinancialDataProvider, MarketDataProvider
from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
    RawFinancialsYear,
)
from backend.providers.normalizers import get_normalizer
from backend.providers.normalizers.base import FinancialNormalizer

logger = logging.getLogger("backend.pipeline")

DEFAULT_HISTORY_YEARS = 10


class PipelineError(Exception):
    """Raised when no provider could produce usable data for a ticker."""


def _usable_count(normalized: list[NormalizedFinancials]) -> int:
    """Years carrying real fundamentals (quality above the shell threshold)."""
    from backend.repositories.source_selection import USABLE_QUALITY_THRESHOLD

    return sum(
        1
        for row in normalized
        if row.data_quality_score is not None
        and row.data_quality_score >= USABLE_QUALITY_THRESHOLD
    )


@dataclass(slots=True)
class LoadResult:
    """Outcome of loading one ticker's financial history."""

    ticker: str
    source: ProviderName
    years_loaded: int
    statements: list[NormalizedFinancials] = field(default_factory=list)
    cached: bool = False
    errors: list[str] = field(default_factory=list)


class DataPipelineService(DataLoader):
    """Fetch-normalize-store pipeline with Yahoo → EDGAR fallback."""

    def __init__(
        self,
        repository: FinancialRepository,
        primary: FinancialDataProvider,
        fallback: FinancialDataProvider | None = None,
        market: MarketDataProvider | None = None,
        normalizers: dict[type, FinancialNormalizer] | None = None,
        company_saver: Callable[[str], None] | None = None,
        default_years: int = DEFAULT_HISTORY_YEARS,
        report_source: ProviderName | None = None,
    ):
        self._repository = repository
        self._primary = primary
        self._fallback = fallback
        self._market = market
        self._normalizers = normalizers or {}
        self._company_saver = company_saver
        self._default_years = default_years
        # When set, LoadResult.source reports this provider regardless of
        # which network provider fetched the raw statements. Used when the
        # repository is read-only Financial-DataBase: the data that actually
        # backs the analysis lives there, so "edgar" is the truthful label
        # even when --force re-downloaded statements from Yahoo.
        self._report_source = report_source

    # ------------------------------------------------------------------
    def _ensure_company(self, ticker: str) -> None:
        if self._company_saver is None:
            return
        try:
            self._company_saver(ticker)
        except Exception:  # noqa: BLE001 — registration must not block the pipeline
            logger.warning("pipeline: could not register company %s", ticker)

    # ------------------------------------------------------------------
    def load_ticker(
        self, ticker: str, years: int | None = None, force: bool = False
    ) -> LoadResult:
        """Ensure normalized data exists, trying providers in order.

        Uses the repository cache when available (unless ``force``), then
        attempts the primary provider (Yahoo) and falls back to the
        secondary (EDGAR) if the primary yields nothing usable.
        """
        ticker = ticker.upper().strip()
        history_years = years if years and years > 0 else self._default_years

        if not force and self._repository.has_data(ticker):
            cached_records = self._repository.list_years(ticker)
            if not cached_records:
                # No cached data, fall through to fetch
                pass
            else:
                # We have cached records, use them directly
                logger.info(
                    "pipeline: %s served from cache (%d years)", ticker, len(cached_records)
                )
                return LoadResult(
                    ticker=ticker,
                    source=self._report_source
                    or (
                        cached_records[0].source
                        if cached_records
                        else ProviderName.YAHOO
                    ),
                    years_loaded=len(cached_records),
                    statements=cached_records,
                    cached=True,
                )

        providers = [self._primary]
        if self._fallback is not None:
            providers.append(self._fallback)

        last_error: str | None = None
        best: tuple[list[NormalizedFinancials], type] | None = None
        for index, provider in enumerate(providers):
            if index > 0 and best is not None:
                # The primary delivered enough usable years; the fallback
                # would only add network cost without improving coverage.
                if _usable_count(best[0]) >= history_years:
                    break
            try:
                raw_years = self._fetch_history(provider, ticker, history_years)
                if not raw_years:
                    last_error = f"{type(provider).__name__} returned no data"
                    logger.warning("pipeline: %s %s", ticker, last_error)
                    continue
                normalized = self._normalize(provider, raw_years)
                if not normalized:
                    last_error = (
                        f"{type(provider).__name__} could not normalize any year"
                    )
                    logger.warning("pipeline: %s %s", ticker, last_error)
                    continue
                if best is None or _usable_count(normalized) > _usable_count(best[0]):
                    best = (normalized, type(provider))
                if _usable_count(normalized) >= history_years:
                    break
            except Exception as exc:  # noqa: BLE001 — provider failures are expected
                last_error = f"{type(provider).__name__}: {exc}"
                logger.exception(
                    "pipeline: %s failed via %s", ticker, type(provider).__name__
                )

        if best is not None:
            normalized, provider_type = best
            self._store(ticker, normalized)
            logger.info(
                "pipeline: %s stored %d years from %s",
                ticker,
                len(normalized),
                provider_type.__name__,
            )
            return LoadResult(
                ticker=ticker,
                source=self._report_source or normalized[0].source,
                years_loaded=len(normalized),
                statements=normalized,
            )

        raise PipelineError(f"No financial data available for {ticker} ({last_error})")

    # ------------------------------------------------------------------
    def _fetch_history(
        self, provider: FinancialDataProvider, ticker: str, years: int
    ) -> list[RawFinancialsYear]:
        """Collect raw statements per fiscal year from one provider."""
        fiscal_years = self._fiscal_year_labels(provider, ticker)
        today_year = datetime.now(timezone.utc).year
        shares = None
        if self._market is not None:
            try:
                shares = self._market.get_shares_outstanding(ticker)
            except Exception:  # noqa: BLE001
                logger.debug("pipeline: shares outstanding unavailable for %s", ticker)

        raw_years: list[RawFinancialsYear] = []
        for index in range(years):
            try:
                income = provider.get_income_statement(ticker, index)
            except Exception:  # noqa: BLE001
                income = None
            try:
                balance = provider.get_balance_sheet(ticker, index)
            except Exception:  # noqa: BLE001
                balance = None
            try:
                cash_flow = provider.get_cash_flow(ticker, index)
            except Exception:  # noqa: BLE001
                cash_flow = None

            if income is None and balance is None and cash_flow is None:
                if index == 0:
                    break
                continue

            year = (
                fiscal_years[index] if index < len(fiscal_years) else today_year - index
            )
            raw_years.append(
                RawFinancialsYear(
                    ticker=ticker,
                    year=year,
                    income=income,
                    balance=balance,
                    cash_flow=cash_flow,
                    shares_outstanding=shares if index == 0 else None,
                )
            )
        return raw_years

    @staticmethod
    def _fiscal_year_labels(provider: FinancialDataProvider, ticker: str) -> list[int]:
        getter = getattr(provider, "get_fiscal_years", None)
        if callable(getter):
            try:
                return getter(ticker)
            except Exception:  # noqa: BLE001
                return []
        return []

    def _normalize(
        self, provider: FinancialDataProvider, raw_years: list[RawFinancialsYear]
    ) -> list[NormalizedFinancials]:
        normalizer = self._normalizers.get(type(provider))
        if normalizer is None:
            normalizer = get_normalizer(provider)
        if normalizer is None:
            raise PipelineError(
                f"No normalizer registered for {type(provider).__name__}"
            )
        return [n for raw in raw_years if (n := normalizer.normalize(raw)) is not None]

    def _store(self, ticker: str, statements: list[NormalizedFinancials]) -> None:
        self._ensure_company(ticker)
        self._repository.upsert_many(statements)
