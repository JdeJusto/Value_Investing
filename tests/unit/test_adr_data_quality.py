"""ADR data quality: ADS ratios, USD cash-flow conversion and IFRS mappings."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.repositories.ads_ratios import ads_ratio_for
from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)


# ---------------------------------------------------------------------------
# Pure helpers / mappings
# ---------------------------------------------------------------------------
def test_ads_ratio_table_and_unknown_fallback():
    assert ads_ratio_for("BABA") == 8.0
    assert ads_ratio_for("PDD") == 4.0
    assert ads_ratio_for("SNY") == 0.5
    assert ads_ratio_for("AAPL") == 1.0
    assert ads_ratio_for(None) == 1.0


def test_core_merge_converts_cny_cash_flow_and_debt_to_usd():
    row = NormalizedFinancials(
        ticker="BABA",
        fiscal_year=2024,
        revenue=941_168_000_000.0,
        operating_cash_flow=182_593_000_000.0,
        capital_expenditure=30_000_000_000.0,
        total_debt=55_861_000_000.0,
    )
    core = {
        "currency": "CNY",
        "revenue_usd": 130_207_914_235.872,
    }

    merged = FinancialDatabaseRepository._merge_core_row(row, core)
    fx = 130_207_914_235.872 / 941_168_000_000.0

    assert merged.operating_cash_flow == pytest.approx(182_593_000_000 * fx)
    assert merged.capital_expenditure == pytest.approx(30_000_000_000 * fx)
    assert merged.free_cash_flow == pytest.approx(
        (182_593_000_000 - 30_000_000_000) * fx
    )
    assert merged.total_debt == pytest.approx(55_861_000_000 * fx)


def _fact(concept, value, unit="CNY"):
    return {
        "concept": concept,
        "value": value,
        "unit": unit,
        "fiscal_year": 2024,
        "fiscal_period": "FY",
        "period_end": date(2024, 3, 31),
        "period_start": date(2023, 4, 1),
    }


def test_ifrs_cash_flow_and_capex_tags_are_mapped():
    repo = FinancialDatabaseRepository()  # normalization needs no query
    statements = repo._normalize_financial_facts(
        [
            _fact("CashFlowsFromUsedInOperatingActivities", 14_575_000_000),
            _fact(
                "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                2_810_000_000,
            ),
        ],
        bucket_year=2024,
    )

    assert statements["cash_flow"]["operating_cash_flow"] == 14_575_000_000
    assert statements["cash_flow"]["capital_expenditure"] == 2_810_000_000


def test_convertible_debt_counts_as_noncurrent_debt():
    repo = FinancialDatabaseRepository()
    statements = repo._normalize_financial_facts(
        [
            _fact("Assets", 1_000.0),
            _fact("StockholdersEquity", 400.0),
            _fact("ConvertibleDebtNoncurrent", 55_861_000_000.0),
        ],
        bucket_year=2024,
    )
    assert statements["balance"]["total_debt"] == 55_861_000_000


# ---------------------------------------------------------------------------
# Live FDB (skipped when unavailable)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def repo():
    repository = FinancialDatabaseRepository()
    if not repository.available():
        pytest.skip("Financial-DataBase is not reachable")
    yield repository
    repository.close()


def test_baba_shares_are_ads_not_ordinary(repo):
    shares = repo.get_shares_outstanding("BABA", 2024)
    assert shares is not None
    assert 2_300_000_000 < shares < 2_600_000_000  # 19.47B ordinary / 8


def test_baba_debt_is_converted_to_usd(repo):
    rows = repo.get_best_available("BABA")
    row = rows[0]  # latest completed year, where convertible debt is non-zero
    assert row.total_debt is not None
    assert 1_000_000_000 < row.total_debt < 20_000_000_000  # CNY 55.9B → USD
    assert row.stockholders_equity is not None
    assert row.total_debt / row.stockholders_equity < 0.5


def test_baba_historical_pe_uses_ads_eps(repo):
    from backend.services.historical_valuation_service import (
        HistoricalValuationService,
    )

    class _Prices:
        def get_price_at_fiscal_year_end(self, ticker, year, end=None):
            return 69.93 if year == 2024 else None

        def get_split_adjustment(self, ticker, end):
            return 1.0

    rows = HistoricalValuationService(repo, _Prices()).get_historical_valuation_summary(
        "BABA"
    )
    fy2024 = next(row for row in rows if row["fiscal_year"] == 2024)
    assert 3.0 < fy2024["eps"] < 6.0
    assert 10.0 < fy2024["pe_ratio"] < 20.0


def test_ifrs_ticker_has_fcf(repo):
    rows = repo.get_best_available("AZN")
    assert rows
    row = rows[0]
    assert row.operating_cash_flow is not None
    assert row.capital_expenditure is not None
    assert row.free_cash_flow is not None


def test_sector_fallback_returns_fdb_sector(monkeypatch):
    from cli.commands.analyze_full import _company_overview

    fake = SimpleNamespace(
        get_company_sector=lambda ticker: "Consumer Cyclical",
        get_company_industry=lambda ticker: "Internet Retail",
    )
    monkeypatch.setattr("backend.app.cli.build_financial_repository", lambda: fake)
    assert _company_overview("BABA", "Alibaba") == (
        "Consumer Cyclical",
        "Internet Retail",
    )
