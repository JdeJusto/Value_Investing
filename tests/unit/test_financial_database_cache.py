"""Unit tests for the FinancialDatabaseRepository run-scoped fundamentals cache.

The cache exists so the two ``analyze`` reads per ticker (``_load_history``
and ``_data_reliability``) share a single facts query + normalization. These
tests verify the caching contract without touching the database (the query
itself is monkeypatched away).
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
        free_cash_flow=5.0,
        shares_outstanding=1_000_000,
    )


def _make_repo(rows_by_ticker, calls=None):
    """Repository whose _list_years_uncached serves rows without touching SQL."""

    class _Stub(FinancialDatabaseRepository):
        def __init__(self):
            super().__init__(database_url="postgresql://stub")
            self._rows_by_ticker = rows_by_ticker

        def available(self):
            return True

        def _list_years_uncached(self, ticker):
            if calls is not None:
                calls.append(ticker)
            return [row for row in self._rows_by_ticker.get(ticker.upper(), [])]

    return _Stub()


def test_second_list_years_call_is_cached():
    calls = []
    repo = _make_repo({"AAPL": [_record("AAPL", 2024), _record("AAPL", 2023)]}, calls)

    first = repo.list_years("AAPL")
    second = repo.list_years("AAPL")

    assert [r.fiscal_year for r in first] == [2024, 2023]
    assert [r.fiscal_year for r in second] == [2024, 2023]
    # One underlying query for two reads.
    assert calls == ["AAPL"]


def test_list_all_and_get_best_available_share_the_cache():
    calls = []
    repo = _make_repo({"MSFT": [_record("MSFT", 2024)]}, calls)

    repo.list_years("MSFT")
    repo.list_all("MSFT")
    repo.get_best_available("MSFT")

    assert calls == ["MSFT"]


def test_invalidate_list_cache_re_fetches():
    calls = []
    repo = _make_repo({"AAPL": [_record("AAPL", 2024)]}, calls)

    repo.list_years("AAPL")
    repo.invalidate_list_cache("AAPL")
    repo.list_years("AAPL")

    assert calls == ["AAPL", "AAPL"]


def test_upsert_invalidates_the_ticker():
    calls = []
    repo = _make_repo({"AAPL": [_record("AAPL", 2024)]}, calls)

    repo.list_years("AAPL")
    repo.upsert(_record("AAPL", 2024))
    repo.list_years("AAPL")

    assert calls == ["AAPL", "AAPL"]


def test_empty_results_are_not_cached():
    calls = []
    repo = _make_repo({"AAPL": []}, calls)

    assert repo.list_years("AAPL") == []
    assert repo.list_years("AAPL") == []

    # Both reads hit the underlying query because negative lookups are never
    # cached (a sync may populate the company in between reads).
    assert calls == ["AAPL", "AAPL"]


def test_cached_rows_are_copied():
    calls = []
    repo = _make_repo({"AAPL": [_record("AAPL", 2024)]}, calls)

    first = repo.list_years("AAPL")
    second = repo.list_years("AAPL")
    assert first is not second  # caller mutations must not poison the cache