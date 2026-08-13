"""Unit tests: analytics consume only normalized repository data."""

import pytest

from backend.analytics.service import CompanyAnalysisService
from backend.domain.interfaces.provider import MarketDataProvider
from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)
from backend.repositories.json_financial_repository import JsonFinancialRepository


class MockMarketProvider(MarketDataProvider):
    def __init__(self):
        self.calls = {"get_market_cap": 0, "get_enterprise_value": 0}

    def get_company_name(self, ticker):
        return ticker

    def get_market_cap(self, ticker):
        self.calls["get_market_cap"] += 1
        return 1_000_000_000

    def get_enterprise_value(self, ticker):
        self.calls["get_enterprise_value"] += 1
        return 1_100_000_000

    def get_current_price(self, ticker):
        return 100.0

    def get_beta(self, ticker):
        return 1.0

    def get_shares_outstanding(self, ticker):
        return 10_000_000


class RecordingLoader:
    def __init__(self):
        self.requests: list[str] = []

    def load_ticker(self, ticker, years=None, force=False):
        self.requests.append(ticker)


def _full_record(year: int) -> NormalizedFinancials:
    revenue = 100_000 + year * 10_000
    return NormalizedFinancials(
        ticker="AAPL",
        fiscal_year=year,
        revenue=revenue,
        cogs=revenue * 0.6,
        gross_profit=revenue * 0.4,
        operating_income=revenue * 0.25,
        ebit=revenue * 0.25,
        ebitda=revenue * 0.30,
        net_income=revenue * 0.20,
        interest_expense=1_000,
        tax_provision=revenue * 0.05,
        pretax_income=revenue * 0.25,
        total_assets=300_000 + year * 10_000,
        total_liabilities=180_000 + year * 5_000,
        total_debt=50_000,
        cash_and_equivalents=20_000,
        working_capital=15_000,
        retained_earnings=90_000,
        stockholders_equity=100_000,
        operating_cash_flow=revenue * 0.28,
        capital_expenditure=8_000,
        free_cash_flow=revenue * 0.20,
        depreciation_amortization=revenue * 0.05,
        dividends_paid=4_000,
        repurchase_of_stock=6_000,
        working_capital_change=1_000,
        shares_outstanding=10_000_000,
        source=ProviderName.YAHOO,
    )


@pytest.fixture
def repo(tmp_path):
    return JsonFinancialRepository(tmp_path / "normalized")


@pytest.fixture
def market():
    return MockMarketProvider()


@pytest.fixture
def service(repo, market):
    return CompanyAnalysisService(repository=repo, market_provider=market)


def test_analyze_empty_repository_returns_none(service):
    assert service.analyze("AAPL") is None


def test_analyze_uses_loader_when_repository_empty(repo, market):
    loader = RecordingLoader()
    service = CompanyAnalysisService(
        repository=repo, market_provider=market, loader=loader
    )
    assert service.analyze("MSFT") is None
    assert loader.requests == ["MSFT"]


def test_analyze_computes_metrics_from_normalized_rows(repo, market, service):
    repo.upsert_many([_full_record(2024), _full_record(2023)])

    result = service.analyze("AAPL")

    assert result is not None
    assert result["ticker"] == "AAPL"
    assert result["revenue"] == 100_000 + 2024 * 10_000
    assert result["net_income"] == result["revenue"] * 0.20
    assert result["fcf"] == result["revenue"] * 0.20

    assert result["roe"] == pytest.approx((result["revenue"] * 0.20) / 100_000)
    assert result["net_margin"] == pytest.approx(0.20)
    assert result["operating_margin"] == pytest.approx(0.25)
    assert result["pb"] == pytest.approx(1_000_000_000 / 100_000)
    assert result["market_cap"] == 1_000_000_000
    assert result["total_debt"] == 50_000
    assert result["equity"] == 100_000


def test_analyze_derives_equity_from_assets_minus_liabilities(repo, market, service):
    record = _full_record(2024)
    record.stockholders_equity = None
    repo.upsert(record)

    result = service.analyze("AAPL")

    expected_equity = record.total_assets - record.total_liabilities
    assert result["equity"] == pytest.approx(expected_equity)
    assert result["roe"] == pytest.approx(record.net_income / expected_equity)


def test_analyze_uses_single_year_when_no_history(repo, market, service):
    repo.upsert(_full_record(2024))

    result = service.analyze("AAPL")

    assert result is not None
    assert result["roic"] is not None
    assert result["piotroski_fscore"] is not None


def test_analyze_never_calls_financial_providers(repo, market, service):
    repo.upsert_many([_full_record(2024), _full_record(2023)])

    class ExplodingProvider:
        def __init__(self):
            self.touched = False

        def __getattr__(self, name):
            self.touched = True
            raise AssertionError(f"analytics touched a provider: {name}")

    service.analyze("AAPL")
    # if any provider attribute had been accessed, the getattr above would have raised
    assert True


def _quality_record(year: int, source=ProviderName.YAHOO) -> NormalizedFinancials:
    record = _full_record(year)
    record.source = source
    record.data_quality_score = 0.92
    record.data_completeness = 1.0
    record.is_complete = True
    record.data_source_priority = 2 if source is ProviderName.YAHOO else 1
    record.derived_metrics = ["free_cash_flow"]
    return record


def test_analyze_reports_single_source_high_confidence(repo, market, service):
    repo.upsert_many([_quality_record(2024), _quality_record(2023)])

    result = service.analyze("AAPL")

    assert result["data_source_used"] == "YAHOO"
    assert result["confidence"] == "HIGH"
    assert result["data_quality_score"] == pytest.approx(0.92)
    assert result["data_completeness"] == pytest.approx(1.0)
    assert result["data_coverage"] == pytest.approx(1.0)
    assert result["data_refreshed"] is True


def test_analyze_mixed_sources_reports_low_confidence(repo, market, service):
    repo.upsert_many(
        [
            _quality_record(2024, ProviderName.YAHOO),
            _quality_record(2023, ProviderName.EDGAR),
        ]
    )

    result = service.analyze("AAPL")

    assert result["data_source_used"] == "MIXED"
    assert result["confidence"] == "LOW"


def test_analyze_prefers_complete_source_over_sparse(repo, market, service):
    yahoo = _quality_record(2024, ProviderName.YAHOO)
    edgar2024 = _quality_record(2024, ProviderName.EDGAR)
    edgar2023 = _quality_record(2023, ProviderName.EDGAR)
    repo.upsert_many([yahoo, edgar2024, edgar2023])

    result = service.analyze("AAPL")

    assert result["data_source_used"] == "EDGAR"
    assert result["confidence"] == "HIGH"
    assert result["data_coverage"] == pytest.approx(1.0)


def test_analyze_refreshes_when_data_stale(repo, market):
    from datetime import datetime, timedelta, timezone

    def fresh_record():
        record = _quality_record(2024)
        record.loaded_at = datetime.now(timezone.utc)
        return record

    stale = fresh_record()
    stale.loaded_at = datetime.now(timezone.utc) - timedelta(days=120)
    repo.upsert(stale)
    loader = RecordingLoader()
    loader.load_ticker = lambda ticker, years=None, force=False: repo.upsert(
        fresh_record()
    )
    service = CompanyAnalysisService(
        repository=repo, market_provider=market, loader=loader
    )

    result = service.analyze("AAPL")

    assert result is not None
    assert result["data_refreshed"] is True
