"""Deterministic chart series for the Streamlit Scorecard tab (Phase 4).

The Scorecard tab shows a six-axis radar plus four history charts. This service
produces the numbers behind those charts so the view stays presentation-only:
every value comes from the same repository, analytics calculators and DCF the
analysis page already uses. Nothing is recomputed in Streamlit.

Prices are read through ``PriceService`` (Yahoo, in-memory cache only) and are
**never persisted**. A missing price or an uncomputable DCF degrades to
``None``; the valuation chart then reads "price unavailable" instead of
erroring.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.analytics.ratios.margins import (
    NetMarginCalculator,
    OperatingMarginCalculator,
)
from backend.analytics.ratios.roe import RoeCalculator
from backend.analytics.ratios.roic import RoicCalculator
from backend.analytics.service import effective_tax_rate
from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.intelligence.quality_metrics import equity_of

#: Newest N fiscal years — the same window the analysis page reads.
DEFAULT_MAX_YEARS = 10


@dataclass(frozen=True)
class YearSeries:
    """One fiscal year's chart values (``None`` where a metric is missing)."""

    fiscal_year: int
    revenue: float | None
    net_income: float | None
    gross_margin: float | None
    operating_margin: float | None
    net_margin: float | None
    roe: float | None
    roic: float | None


@dataclass(frozen=True)
class ScorecardCharts:
    """The four history charts' payload plus the DCF-vs-price point.

    The radar itself is built from the scorecard's dimension scores; this
    payload only carries the fundamentals history. Tuples keep the dataclass
    hashable/serializable for Streamlit's cacher.
    """

    ticker: str
    years: tuple[YearSeries, ...]
    dcf_value: float | None
    price: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScorecardChartService:
    """Build the Scorecard tab's chart series for one ticker."""

    def __init__(
        self,
        repository: Any,
        price_service: Any | None = None,
        max_years: int = DEFAULT_MAX_YEARS,
    ) -> None:
        self._repository = repository
        self._price_service = price_service
        self._max_years = max_years

    def build(self, ticker: str) -> ScorecardCharts | None:
        """Return the chart series, or ``None`` when there are no fundamentals."""
        rows = self._rows(ticker)
        if not rows:
            return None
        dcf_value, price = self._dcf(ticker, rows)
        return ScorecardCharts(
            ticker=ticker.upper(),
            years=tuple(_year_series(row) for row in rows),
            dcf_value=dcf_value,
            price=price,
        )

    def _rows(self, ticker: str) -> list[NormalizedFinancials]:
        """Usable fiscal years, oldest first, empty buckets dropped."""
        try:
            fetched = self._repository.get_best_available(
                ticker, max_years=self._max_years
            )
        except Exception:  # noqa: BLE001 — no history is not a crash
            return []
        rows = [
            row
            for row in fetched
            if row is not None
            and (row.revenue is not None or row.net_income is not None)
        ]
        rows.sort(key=lambda row: row.fiscal_year)
        return rows

    def _dcf(
        self, ticker: str, rows: list[NormalizedFinancials]
    ) -> tuple[float | None, float | None]:
        if self._price_service is None:
            return None, None
        try:
            from backend.valuation.dcf import DCFValuation

            result = DCFValuation().evaluate(ticker, rows, self._price_service)
        except Exception:  # noqa: BLE001 — a missing DCF is not a crash
            return None, None
        return (
            getattr(result, "intrinsic_value_per_share", None),
            getattr(result, "current_price", None),
        )


def _year_series(row: NormalizedFinancials) -> YearSeries:
    equity = equity_of(row)
    revenue = row.revenue
    return YearSeries(
        fiscal_year=row.fiscal_year,
        revenue=revenue,
        net_income=row.net_income,
        gross_margin=_gross_margin(row),
        operating_margin=OperatingMarginCalculator().calculate(
            operating_income=row.operating_income, revenue=revenue
        ),
        net_margin=NetMarginCalculator().calculate(
            net_income=row.net_income, revenue=revenue
        ),
        roe=RoeCalculator().calculate(net_income=row.net_income, equity=equity),
        roic=RoicCalculator().calculate(
            ebit=row.ebit,
            tax_rate=effective_tax_rate(row),
            total_debt=row.total_debt,
            equity=equity,
            cash=row.cash_and_equivalents,
        ),
    )


def _gross_margin(row: NormalizedFinancials) -> float | None:
    """(revenue - cogs) / revenue, the same formula the analysis page uses."""
    if row.revenue and row.cogs is not None:
        return (row.revenue - row.cogs) / row.revenue
    return None
