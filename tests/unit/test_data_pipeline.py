"""Unit tests for the data pipeline (all providers mocked, no network)."""

import pytest

from backend.domain.entities.financials import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
)
from backend.domain.interfaces.provider import FinancialDataProvider, MarketDataProvider
from backend.domain.value_objects.financials_normalized import (
    ProviderName,
    RawFinancialsYear,
)
from backend.providers.normalizers.yahoo_normalizer import YahooNormalizer
from backend.repositories.json_financial_repository import JsonFinancialRepository
from backend.services.data_pipeline_service import DataPipelineService, PipelineError


class MockMarketProvider(MarketDataProvider):
    def __init__(self, shares=1_000_000_000):
        self.shares = shares

    def get_company_name(self, ticker):
        return ticker

    def get_market_cap(self, ticker):
        return 1_000_000_000

    def get_enterprise_value(self, ticker):
        return 900_000_000

    def get_current_price(self, ticker):
        return 10.0

    def get_beta(self, ticker):
        return 1.0

    def get_shares_outstanding(self, ticker):
        return self.shares


class MockYahooProvider(FinancialDataProvider):
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = 0

    def _maybe_fail(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("yahoo down")

    def get_income_statement(self, ticker, year_index=0):
        self._maybe_fail()
        if year_index >= 3:
            return None
        return IncomeStatement(
            revenue=100 + year_index,
            operating_income=30 - year_index,
            ebit=30 - year_index,
            net_income=20 - year_index,
        )

    def get_balance_sheet(self, ticker, year_index=0):
        self._maybe_fail()
        if year_index >= 3:
            return None
        return BalanceSheet(
            total_assets=500 - year_index * 10,
            total_liabilities=300 - year_index * 10,
            stockholders_equity=200,
        )

    def get_cash_flow(self, ticker, year_index=0):
        self._maybe_fail()
        if year_index >= 3:
            return None
        return CashFlowStatement(
            operating_cash_flow=50 - year_index,
            capital_expenditure=10,
            free_cash_flow=40 - year_index,
        )

    def get_fiscal_years(self, ticker):
        return [2025, 2024, 2023, 2022, 2021]


class MockEdgarProvider(FinancialDataProvider):
    def __init__(self, data_available: bool = True):
        self.data_available = data_available

    def get_income_statement(self, ticker, year_index=0):
        if not self.data_available or year_index > 0:
            return None
        return IncomeStatement(revenue=999, ebit=300, net_income=250)

    def get_balance_sheet(self, ticker, year_index=0):
        if not self.data_available or year_index > 0:
            return None
        return BalanceSheet(total_assets=1000, total_liabilities=600)

    def get_cash_flow(self, ticker, year_index=0):
        if not self.data_available or year_index > 0:
            return None
        return CashFlowStatement(operating_cash_flow=200, free_cash_flow=150)


@pytest.fixture
def repo(tmp_path):
    return JsonFinancialRepository(tmp_path / "normalized")


@pytest.fixture
def pipeline(repo):
    return DataPipelineService(
        repository=repo,
        primary=MockYahooProvider(),
        fallback=MockEdgarProvider(),
        market=MockMarketProvider(),
        normalizers={MockYahooProvider: YahooNormalizer()},
        default_years=5,
    )


def test_load_ticker_fetches_normalizes_and_persists(pipeline, repo):
    result = pipeline.load_ticker("AAPL")

    assert result.years_loaded == 3
    assert result.source == ProviderName.YAHOO
    assert result.cached is False

    records = repo.list_years("AAPL")
    assert len(records) == 3
    assert [r.fiscal_year for r in records] == [2025, 2024, 2023]
    assert records[0].revenue == 100
    assert records[0].net_income == 20
    assert records[0].total_assets == 500
    assert records[0].free_cash_flow == 40
    assert records[0].source == ProviderName.YAHOO
    assert records[0].shares_outstanding == 1_000_000_000


def test_load_ticker_uses_cache_without_refetch(pipeline, repo):
    pipeline.load_ticker("AAPL")
    result = pipeline.load_ticker("AAPL")

    assert result.cached is True
    assert result.years_loaded == 3


def test_load_ticker_force_refetches(pipeline, repo):
    pipeline.load_ticker("AAPL")
    result = pipeline.load_ticker("AAPL", force=True)

    assert result.cached is False


def test_primary_failure_falls_back_to_edgar(tmp_path):
    repo = JsonFinancialRepository(tmp_path / "normalized")
    yahoo_normalizer = YahooNormalizer()
    service = DataPipelineService(
        repository=repo,
        primary=MockYahooProvider(fail=True),
        fallback=MockEdgarProvider(),
        normalizers={
            MockYahooProvider: yahoo_normalizer,
            MockEdgarProvider: yahoo_normalizer,
        },
    )

    result = service.load_ticker("MSFT")

    assert result.years_loaded == 1
    records = repo.list_years("MSFT")
    assert len(records) == 1
    assert records[0].revenue == 999


def test_both_providers_fail_raises_pipeline_error(tmp_path):
    repo = JsonFinancialRepository(tmp_path / "normalized")
    service = DataPipelineService(
        repository=repo,
        primary=MockYahooProvider(fail=True),
        fallback=MockEdgarProvider(data_available=False),
        normalizers={MockYahooProvider: YahooNormalizer()},
    )

    with pytest.raises(PipelineError):
        service.load_ticker("MSFT")


def test_no_normalizer_registered_raises(tmp_path):
    repo = JsonFinancialRepository(tmp_path / "normalized")
    service = DataPipelineService(
        repository=repo,
        primary=MockYahooProvider(),
        fallback=MockEdgarProvider(),
        normalizers={},  # registry intentionally empty
    )

    with pytest.raises(PipelineError, match="No normalizer registered"):
        service.load_ticker("MSFT")


def test_load_ticker_uppercases_ticker(pipeline, repo):
    pipeline.load_ticker("aapl")
    assert repo.has_data("AAPL")


def test_empty_provider_history_is_skipped(tmp_path):
    class EmptyProvider(MockYahooProvider):
        def get_income_statement(self, ticker, year_index=0):
            return None

        def get_balance_sheet(self, ticker, year_index=0):
            return None

        def get_cash_flow(self, ticker, year_index=0):
            return None

    repo = JsonFinancialRepository(tmp_path / "normalized")
    yahoo_normalizer = YahooNormalizer()
    service = DataPipelineService(
        repository=repo,
        primary=EmptyProvider(),
        fallback=MockEdgarProvider(),
        normalizers={
            EmptyProvider: yahoo_normalizer,
            MockEdgarProvider: yahoo_normalizer,
        },
    )

    service.load_ticker("AAPL")
    records = repo.list_years("AAPL")
    assert len(records) == 1
    assert records[0].revenue == 999


def test_raw_year_bundle_contract():
    raw = RawFinancialsYear(ticker="X", year=2024, income=IncomeStatement(revenue=1))
    assert raw.year == 2024
    assert raw.is_empty() is False
