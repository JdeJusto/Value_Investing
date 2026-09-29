"""Hermetic tests for ``get_best_available`` all-empty row filtering.

A fiscal_year bucket rebuilt from only stray non-income facts (e.g. an
in-progress year fed by an 8-K — NetFeeAmt/TtlFeeAmt/...) is all-empty
(no revenue, net income, assets or shares) and must never be served as the
latest usable year. These tests cover the filtering without touching the
database (the lookup itself is monkeypatched away).
"""

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)


def _record(ticker: str, year: int) -> NormalizedFinancials:
    return NormalizedFinancials(
        ticker=ticker,
        fiscal_year=year,
        revenue=100.0,
        net_income=10.0,
        total_assets=1_000_000.0,
        shares_outstanding=1_000_000,
    )


def _empty(ticker: str, year: int) -> NormalizedFinancials:
    # Only stray non-income facts made it into this bucket.
    return NormalizedFinancials(ticker=ticker, fiscal_year=year)


def _make_repo(rows):
    """Repository whose _list_years_uncached serves rows without touching SQL."""

    class _Stub(FinancialDatabaseRepository):
        def __init__(self):
            super().__init__(database_url="postgresql://stub")

        def _list_years_uncached(self, ticker):
            return list(rows)

    return _Stub()


def test_get_best_available_skips_all_empty_row():
    # Stray FY2026 row shadows a complete FY2025 — must not anchor analysis.
    repo = _make_repo([_empty("XOM", 2026), _record("XOM", 2025)])

    years = [r.fiscal_year for r in repo.get_best_available("XOM")]

    assert years == [2025]


def test_get_best_available_returns_non_empty_rows_by_year_desc():
    repo = _make_repo(
        [
            _empty("X", 2026),
            _empty("X", 2025),
            _record("X", 2024),
            _record("X", 2023),
        ]
    )

    years = [r.fiscal_year for r in repo.get_best_available("X")]

    assert years == [2024, 2023]


def test_get_best_available_all_rows_empty_returns_empty_list():
    repo = _make_repo([_empty("X", 2026), _empty("X", 2025)])

    assert repo.get_best_available("X") == []


def test_get_best_available_no_rows_returns_empty_list():
    repo = _make_repo([])

    assert repo.get_best_available("X") == []


def test_row_is_empty_checks_core_fields():
    assert FinancialDatabaseRepository._row_is_empty(_empty("X", 2026))
    assert not FinancialDatabaseRepository._row_is_empty(_record("X", 2025))

    # A single core field populated makes the row usable.
    partial = NormalizedFinancials(ticker="X", fiscal_year=2026, revenue=1.0)
    assert not FinancialDatabaseRepository._row_is_empty(partial)
