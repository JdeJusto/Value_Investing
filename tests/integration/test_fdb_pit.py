"""Point-in-time reads against the live Financial-DataBase 0.4.0.

Skipped when FDB is not reachable or the 0.4.0 tables are absent. These are
integration checks: they assert the PIT semantics the research backtest relies
on, not parser details.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)


@pytest.fixture(scope="module")
def repo():
    repository = FinancialDatabaseRepository()
    if not repository.available():
        pytest.skip("Financial-DataBase is not reachable")
    if not repository.historical_universe_available():
        pytest.skip("Financial-DataBase 0.4.0 (sp500_constituents) is not loaded")
    yield repository
    repository.close()


def test_point_in_time_excludes_filings_after_the_as_of_date(repo):
    history = repo.list_years_pit("AAPL", date(2018, 1, 1))
    assert history, "AAPL should have FY history before 2018"
    assert max(row.fiscal_year for row in history) <= 2017


def test_point_in_time_fy2018_revenue_is_the_original_10k(repo):
    history = repo.list_years_pit("AAPL", date(2019, 1, 1))
    fy2018 = next(row for row in history if row.fiscal_year == 2018)
    # Apple FY2018 10-K (filed 2018-11-05): $265.595B.
    assert fy2018.revenue == pytest.approx(265_595_000_000.0)


def test_core_financials_pit_accepts_a_ticker_or_uuid(repo):
    by_ticker = repo.get_core_financials_pit("AAPL", 2018, date(2019, 1, 1))
    assert by_ticker is not None
    assert by_ticker["revenue"] == pytest.approx(265_595_000_000.0)
    assert by_ticker["liabilities_effective"] is not None


def test_universe_contains_aapl_in_2015_and_has_plausible_size(repo):
    members = repo.get_sp500_universe(date(2015, 12, 31))
    assert "AAPL" in members
    assert 450 <= len(members) <= 520


def test_universe_follows_removals(repo):
    # Twitter was removed from the index in 2022 and is still in the table.
    assert "TWTR" in repo.get_sp500_universe(date(2022, 6, 30))
    assert "TWTR" not in repo.get_sp500_universe(date(2023, 6, 30))
