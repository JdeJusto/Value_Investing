"""Normalized financial value objects.

This module defines the single canonical representation of a company's
annual financials, decoupled from any provider-specific format (Yahoo,
EDGAR, future providers). All analytics, scoring and valuation layers MUST
consume :class:`NormalizedFinancials` and MUST never touch provider objects.

This is a pure domain module: no pandas, no network, no database.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from backend.domain.entities.financials import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
)


class ProviderName(str, Enum):
    """Identifies the source provider of a normalized record."""

    YAHOO = "yahoo"
    EDGAR = "edgar"


ANNUAL_PERIOD = "FY"


@dataclass(slots=True)
class NormalizedFinancials:
    """Canonical, provider-agnostic annual financial snapshot.

    Field names follow the existing domain vocabulary so analytics layers
    (ratios, scoring, valuation) can rely on a stable contract while the
    underlying data sources evolve or new ones are added.

    All magnitudes are expressed in the statement currency (USD by default).
    ``capital_expenditure`` is normalized to a positive magnitude.
    """

    ticker: str
    fiscal_year: int

    # --- Income statement ------------------------------------------------
    revenue: float | None = None
    cogs: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    ebit: float | None = None
    ebitda: float | None = None
    net_income: float | None = None
    interest_expense: float | None = None
    tax_provision: float | None = None
    pretax_income: float | None = None
    # Additional income statement fields
    operating_expense: float | None = None
    research_development: float | None = None
    sga: float | None = None
    non_operating_income_expense: float | None = None

    # --- Balance sheet ---------------------------------------------------
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_debt: float | None = None
    long_term_debt: float | None = None
    inventory: float | None = None
    cash_and_equivalents: float | None = None
    # current_assets / current_liabilities are the balance-sheet split the
    # Graham criteria need; working_capital stays a stored field for
    # backwards compatibility (criteria 2 and 3 derive it from the split
    # when both sides are present).
    current_assets: float | None = None
    current_liabilities: float | None = None
    working_capital: float | None = None
    retained_earnings: float | None = None
    stockholders_equity: float | None = None

    # --- Cash flow -------------------------------------------------------
    operating_cash_flow: float | None = None
    capital_expenditure: float | None = None
    free_cash_flow: float | None = None
    depreciation_amortization: float | None = None
    dividends_paid: float | None = None
    #: Preferred dividends from the income statement (``DividendsPreferredStock``
    #: / ``PreferredStockDividendsAndOtherAdjustments``); used by the DDM to
    #: subtract preferred from the total dividend base for financials.
    preferred_dividends: float | None = None
    repurchase_of_stock: float | None = None
    working_capital_change: float | None = None

    # --- Context ---------------------------------------------------------
    shares_outstanding: int | None = None
    #: GICS-like sector label (e.g. "Technology", "Financial Services",
    #: "Real Estate"); supplied by the Financial-DataBase company metadata
    #: when available, else None. Consumers must treat None as "unknown
    #: sector", never as a specific sector.
    sector: str | None = None
    # Multiplier that restates this row's as-reported ``shares_outstanding``
    # on today's post-split basis: the product of every stock-split ratio
    # that took effect AFTER this row's fiscal year end. A 4:1 split means a
    # pre-split share is worth 4 current shares, so past as-reported counts
    # multiply by the factor. 1.0 when the filer reports no split ratio (or
    # no split occurred after the row's year) — the count stays as-reported.
    split_adjustment_factor: float = 1.0
    period: str = ANNUAL_PERIOD
    currency: str = "USD"
    source: ProviderName = ProviderName.YAHOO
    loaded_at: datetime | None = None

    # --- Data quality ----------------------------------------------------
    data_completeness: float | None = None
    data_quality_score: float | None = None
    is_complete: bool = False
    data_source_priority: int = 0
    derived_metrics: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict (nan-free, ISO dates)."""
        data = dict(asdict(self))
        source = data.pop("source")
        data["source"] = (
            source.value if isinstance(source, ProviderName) else str(source)
        )
        data.pop("as_currency", None)
        loaded_at = data.pop("loaded_at", None)
        if loaded_at is not None:
            if isinstance(loaded_at, datetime):
                data["loaded_at"] = loaded_at.isoformat()
            else:
                data["loaded_at"] = str(loaded_at)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedFinancials:
        """Rebuild an object from :meth:`to_dict` output (and JSON storage)."""
        clean: dict[str, Any] = {}
        known = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key not in known:
                continue
            if key == "source":
                try:
                    value = ProviderName(str(value).lower())
                except ValueError:
                    value = ProviderName.YAHOO
            elif key == "loaded_at" and value:
                try:
                    value = datetime.fromisoformat(str(value))
                except ValueError:
                    value = None
            clean[key] = value
        if clean.get("loaded_at") is None:
            clean["loaded_at"] = datetime.now(UTC)
        return cls(**clean)


@dataclass(slots=True)
class RawFinancialsYear:
    """Bundle of provider-fetched raw statements for a single fiscal year.

    This is the contract between providers (raw data) and normalizers
    (conversion to :class:`NormalizedFinancials`). All fields are optional:
    a provider may not have data for every statement.
    """

    ticker: str
    year: int
    income: IncomeStatement | None = None
    balance: BalanceSheet | None = None
    cash_flow: CashFlowStatement | None = None
    shares_outstanding: int | float | None = None

    def is_empty(self) -> bool:
        return self.income is None and self.balance is None and self.cash_flow is None
