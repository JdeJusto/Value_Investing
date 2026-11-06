"""Regression tests for the fiscal-year window anchor (C2).

A stray in-progress FY2026 bucket used to make ``_min_fiscal_year`` start a
10-year window at 2017, hiding FY2016 and breaking the "10 years ago" checks.
The window must anchor on the last *usable* year (Assets + Equity in
``core_financials``), falling back to the raw maximum only when the core layer
has no usable row.
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.repositories.fdb_mixins.facts_mixin import FactsMixin
from backend.services.scorecard_service import ScorecardService


class _FakeCursor:
    """Small cursor double for the two queries in ``_min_fiscal_year``."""

    def __init__(self, core_anchor: int | None, raw_max: int | None) -> None:
        self.core_anchor = core_anchor
        self.raw_max = raw_max
        self.queries: list[str] = []

    def execute(self, sql: str, params=None) -> None:
        self.queries.append(sql)

    def fetchone(self):
        last = self.queries[-1]
        if "core_financials" in last:
            if self.core_anchor is None:
                return None
            return {"fiscal_year": self.core_anchor}
        if self.raw_max is None:
            return None
        return {"max_fy": self.raw_max}


def test_min_fiscal_year_anchors_on_effective_year():
    """NEE-style stray FY2026: 11 rows start at 2015, not 2016/2017."""
    cursor = _FakeCursor(core_anchor=2025, raw_max=2026)

    assert FactsMixin._min_fiscal_year(cursor, "company-id", max_years=11) == 2015
    assert "core_financials" in cursor.queries[0]
    assert len(cursor.queries) == 1  # core anchor wins; raw fallback untouched


def test_min_fiscal_year_ten_year_dimension_window_starts_at_2016():
    """The dimensions keep 10 rows; the stray FY2026 must not hide FY2016."""
    cursor = _FakeCursor(core_anchor=2025, raw_max=2026)

    assert FactsMixin._min_fiscal_year(cursor, "company-id", max_years=10) == 2016


def test_min_fiscal_year_falls_back_to_raw_max_without_core():
    cursor = _FakeCursor(core_anchor=None, raw_max=2026)

    assert FactsMixin._min_fiscal_year(cursor, "company-id", max_years=10) == 2017
    assert "core_financials" in cursor.queries[0]
    assert "MAX(fiscal_year)" in cursor.queries[1]


def test_min_fiscal_year_returns_none_without_facts():
    cursor = _FakeCursor(core_anchor=None, raw_max=None)

    assert FactsMixin._min_fiscal_year(cursor, "company-id", max_years=10) is None


class _FakeRepository:
    def __init__(self) -> None:
        self.max_years_calls: list[int] = []
        self._rows = [
            NormalizedFinancials(
                ticker="T",
                fiscal_year=2024,
                revenue=100.0,
                net_income=10.0,
                total_assets=500.0,
                stockholders_equity=200.0,
            ),
            NormalizedFinancials(
                ticker="T",
                fiscal_year=2023,
                revenue=90.0,
                net_income=9.0,
                total_assets=450.0,
                stockholders_equity=180.0,
            ),
        ]

    def get_best_available(self, ticker: str, max_years: int = 10):
        self.max_years_calls.append(max_years)
        return list(self._rows)

    def get_company_name(self, ticker: str) -> str:
        return "Test Co"


class _FakePrices:
    def get_current_price(self, ticker: str) -> float:
        return 100.0

    def get_market_cap(self, ticker: str) -> float:
        return 1000.0


def test_scorecard_requests_11_rows_for_methodologies():
    """Dimensions keep 10 rows; the methodology evaluator gets 11."""
    repository = _FakeRepository()
    card = ScorecardService(repository=repository, price_service=_FakePrices()).build(
        "T"
    )

    assert card is not None
    assert repository.max_years_calls == [10, 11]
