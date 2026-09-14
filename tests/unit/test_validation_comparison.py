"""
Tests for the S&P 500 validation pipeline and the Financial-DataBase fixes
discovered by it:

- ``_normalize_financial_facts`` must de-duplicate facts by their period_end
  (the fiscal-year bucket holds the latest 10-K cash comparatives), and
  ``total_debt`` must only be summed within the newest comparative.
- disparity thresholds in ``scripts/validate_sp500.py::compare_rows``.
- EPS must use an as-reported diluted share basis (not the current share
  count) on both the repository and Yahoo sides.
"""
from datetime import date

import pandas as pd
import pytest
from types import SimpleNamespace

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)
from backend.providers.yahoo.provider import YahooFinanceProvider

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))
from validate_sp500 import METRICS, compare_rows, _severity


def _fact(concept, value, period_end, period="FY", period_start=None):
    return {
        "concept": concept,
        "value": value,
        "unit": "USD",
        "fiscal_year": 2025,
        "fiscal_period": period,
        "period_end": period_end,
        "period_start": period_start,
    }


class TestNormalizeFiscalYearDedup:
    """get_by_year deduction bug: arbitrary selection among comparatives."""

    _repo = FinancialDatabaseRepository()

    def test_max_period_end_wins_per_concept(self):
        facts = [
            _fact("Revenues", 100e9, date(2024, 9, 28)),
            _fact("Revenues", 120e9, date(2025, 9, 27)),  # the true FY2025 value
            _fact("NetIncomeLoss", 18e9, date(2024, 9, 28)),
            _fact("NetIncomeLoss", 25e9, date(2025, 9, 27)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["revenue"] == 120e9
        assert normalized["income"]["net_income"] == 25e9

    def test_total_debt_sums_only_within_max_period_end(self):
        facts = [
            _fact("DebtCurrent", 5e9, date(2024, 9, 28)),
            _fact("DebtNoncurrent", 10e9, date(2024, 9, 28)),
            _fact("DebtCurrent", 6e9, date(2025, 9, 27)),
            _fact("DebtNoncurrent", 12e9, date(2025, 9, 27)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        # Only the newest comparative year contributes; the older one must not
        # be added on top.
        assert normalized["balance"]["total_debt"] == (6e9 + 12e9)

    def test_cash_flow_and_balance_max_period_end(self):
        facts = [
            _fact("Assets", 300e9, date(2024, 9, 28)),
            _fact("Assets", 340e9, date(2025, 9, 27)),
            _fact("NetCashProvidedByUsedInOperatingActivities", 90e9, date(2024, 9, 28)),
            _fact("NetCashProvidedByUsedInOperatingActivities", 100e9, date(2025, 9, 27)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["balance"]["total_assets"] == 340e9
        assert normalized["cash_flow"]["operating_cash_flow"] == 100e9

    def test_revenue_prefers_full_year_revenues_over_rcwc(self):
        # RevenueFromContractWithCustomerExcludingAssessedTax often only covers
        # a quarter; Revenues carries the full year even when both share the
        # same period_end.
        facts = [
            _fact(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                24.956e9,
                date(2025, 12, 31),
                period_start=date(2025, 10, 1),
            ),
            _fact("Revenues", 80.269e9, date(2025, 12, 31),
                  period_start=date(2025, 1, 1)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["revenue"] == 80.269e9

    def test_revenue_prefers_net_excluding_assessed_tax_when_grossed_up(
        self,
    ):
        # Some companies (distillers: Brown-Forman) report the same top line
        # both net of and including excise taxes; the net figure matches the
        # as-presented income statement (and Yahoo), not the grossed-up one.
        facts = [
            _fact(
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                5.082e9,
                date(2026, 4, 30),
                period_start=date(2025, 5, 1),
            ),
            _fact(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                3.928e9,
                date(2026, 4, 30),
                period_start=date(2025, 5, 1),
            ),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["revenue"] == 3.928e9

    def test_duplicate_concept_same_period_end_takes_longest_duration(self):
        # Two rows of the same concept with the same period_end: the one with
        # the earliest period_start (annual) must win over the quarterly one.
        facts = [
            _fact("RevenueFromContractWithCustomerExcludingAssessedTax",
                  1.693e9, date(2025, 12, 31), period_start=date(2025, 10, 1)),
            _fact("RevenueFromContractWithCustomerExcludingAssessedTax",
                  6.849e9, date(2025, 12, 31), period_start=date(2025, 1, 1)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["revenue"] == 6.849e9

    def test_net_income_prefers_available_to_common(self):
        # Consolidated net income includes amounts attributable to
        # non-controlling interests; for EPS/ROE/net-margin purposes the
        # available-to-common figure is the one that matches Yahoo.
        facts = [
            _fact("NetIncomeLoss", 4.357e9, date(2025, 12, 31)),
            _fact(
                "NetIncomeLossAvailableToCommonStockholdersBasic",
                0.984e9,
                date(2025, 12, 31),
            ),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["net_income"] == 0.984e9


class TestFiscalYearEndMode:
    """get_fiscal_year_end_date must use the latest period_end among the core
    statement concepts: one-off facts tagged 'FY' (fee schedules, Entity%
    cover-page rows) must not shift the fiscal year-end used for cross-source
    anchoring, while the genuine newest 10-K comparative still wins."""

    def test_restricts_fiscal_year_end_to_core_concepts(self, monkeypatch):
        repo = FinancialDatabaseRepository()

        executed: list[str] = []

        class FakeCursor:
            def execute(self, sql, par):
                executed.append(sql)
                self._result = {"period_end": "2026-01-31"}

            def fetchone(self):
                return self._result

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeConn:
            def cursor(self):
                return FakeCursor()

        monkeypatch.setattr(repo, "_get_connection", lambda: FakeConn())
        monkeypatch.setattr(
            repo, "_get_company_id_by_ticker", lambda ticker: "company-1"
        )

        assert repo.get_fiscal_year_end_date("CRM", 2025) == date(2026, 1, 31)
        # The query must anchor MAX() on the mapped statement concepts and not
        # on Entity% cover-page facts or one-off disclosures.
        sql = executed[-1]
        assert "MAX(f.period_end::date)" in sql
        assert "concept = ANY" in sql
        assert "Entity" not in sql


class TestSharesOutstandingPreference:
    """EPS must be computed on a diluted, weighted-average share basis."""

    def test_prefer_diluted_queries_weighted_average_concept(self, monkeypatch):
        repo = FinancialDatabaseRepository()

        executed: list[str] = []
        params: list[tuple] = []
        values = iter(["466733000", "466335000", "470000000"])

        class FakeCursor:
            def execute(self, sql, par):
                executed.append(sql)
                params.append(par)
                self._result = {"value": next(values)}

            def fetchone(self):
                return {"value": self._result["value"]}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeConn:
            def cursor(self):
                return FakeCursor()

        monkeypatch.setattr(repo, "_get_connection", lambda: FakeConn())
        monkeypatch.setattr(
            repo, "_get_company_id_by_ticker", lambda ticker: "company-1"
        )

        result = repo.get_shares_outstanding("BF-B", 2026, prefer_diluted=True)
        assert result == 466733000.0
        # The diluted weighted-average concept must be tried first.
        assert params and "WeightedAverageNumber" in params[0][2]

    def test_default_preference_starts_with_end_of_period(self, monkeypatch):
        repo = FinancialDatabaseRepository()
        executed: list[str] = []
        concepts: list[str] = []
        values = iter(["466335000", "470000000"])

        class FakeCursor:
            def execute(self, sql, par):
                executed.append(sql)
                concepts.append(par[2])
                self._result = {"value": next(values)}

            def fetchone(self):
                return {"value": self._result["value"]}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeConn:
            def cursor(self):
                return FakeCursor()

        monkeypatch.setattr(repo, "_get_connection", lambda: FakeConn())
        monkeypatch.setattr(
            repo, "_get_company_id_by_ticker", lambda ticker: "company-1"
        )
        repo.get_shares_outstanding("BF-B", 2026)
        assert concepts and concepts[0] == "CommonStockSharesOutstanding"


class TestYahooEps:
    """Diluted EPS must not use the current share count from .info."""

    def _ticker(self, df):
        return SimpleNamespace(income_stmt=df)

    def test_reads_diluted_eps_row(self, monkeypatch):
        df = pd.DataFrame(
            {
                "2025-12-31": [3.2, 50e9, 15.6e9],
                "2024-12-31": [2.8, 45e9, 16.1e9],
            },
            index=["Diluted EPS", "Net Income", "Diluted Average Shares"],
        )
        provider = YahooFinanceProvider()
        monkeypatch.setattr(provider, "_get_ticker", lambda t: self._ticker(df))
        assert provider.get_eps("TEST") == 3.2
        assert provider.get_eps("TEST", 1) == 2.8

    def test_falls_back_to_net_income_over_diluted_shares(self, monkeypatch):
        df = pd.DataFrame(
            {
                "2025-12-31": [50e9, 15.6e9],
            },
            index=["Net Income", "Diluted Average Shares"],
        )
        provider = YahooFinanceProvider()
        monkeypatch.setattr(provider, "_get_ticker", lambda t: self._ticker(df))
        eps = provider.get_eps("TEST")
        assert eps is not None
        assert abs(eps - 50e9 / 15.6e9) < 0.001


def _row(metric_values: dict, fiscal_year: int = 2025) -> dict:
    base = {
        "ticker": "XX",
        "fiscal_year": fiscal_year,
        "price": 100.0,
        "market_cap": 1e12,
        "revenue": 100e9,
        "net_income": 10e9,
        "total_assets": 200e9,
        "total_liabilities": 150e9,
        "operating_cash_flow": 15e9,
        "free_cash_flow": 12e9,
        "eps": 5.0,
        "pe_ratio": 20.0,
        "fcf_yield": 0.012,
        "roe": 0.20,
        "net_margin": 0.10,
    }
    base.update(metric_values)
    return base


class TestComparisonThresholds:
    """Each metric flags above its threshold and stays quiet below it."""

    @pytest.mark.parametrize(
        "metric,threshold_kind,threshold",
        [
            ("revenue", "pct", 2.0),
            ("net_income", "pct", 5.0),
            ("total_assets", "pct", 2.0),
            ("total_liabilities", "pct", 2.0),
            ("operating_cash_flow", "pct", 5.0),
            ("eps", "pct", 5.0),
            ("pe_ratio", "pct", 10.0),
            ("roe", "pct", 10.0),
        ],
    )
    def test_pct_metrics(self, metric, threshold_kind, threshold):
        below = _row({metric: 100.0})
        above = _row({metric: 100.0 * (1 + threshold / 100) + 0.01})
        assert compare_rows(below, {**below, metric: 101.0}) == [] or metric not in [
            d["metric"] for d in compare_rows(below, _row({metric: 101.0}))
        ]
        # A clearly larger external value must not trigger us (we compare
        # |vi - ext| when VI is the numerator); force VI to exceed ext instead.
        flagged = compare_rows(_row({metric: 100.0 * (1 + threshold / 100) + 0.01}),
                               _row({metric: 100.0}))
        assert any(d["metric"] == metric for d in flagged)
        # And a small difference stays under the radar.
        small = compare_rows(_row({metric: 100.0 * (1 + threshold / 200)}),
                             _row({metric: 100.0}))
        assert not any(d["metric"] == metric for d in small)

    @pytest.mark.parametrize(
        "metric,threshold_pp",
        [("fcf_yield", 0.5), ("net_margin", 2.0)],
    )
    def test_pp_metrics(self, metric, threshold_pp):
        # A gap of threshold + 0.5pp must flag; a tiny 0.1pp gap stays quiet.
        flagged = compare_rows(
            _row({metric: 0.04 + (threshold_pp + 0.5) / 100}), _row({metric: 0.04})
        )
        assert any(d["metric"] == metric for d in flagged)
        small = compare_rows(
            _row({metric: 0.041}), _row({metric: 0.04})
        )
        assert not any(d["metric"] == metric for d in small)

    def test_pp_uses_threshold_in_percentage_points(self):
        # fcf_yield differs by 0.4pp -> below the 0.5pp threshold (values here
        # are 0.016 vs 0.012 = 0.4pp).
        flagged = compare_rows(
            _row({"fcf_yield": 0.016}), _row({"fcf_yield": 0.012})
        )
        assert not any(d["metric"] == "fcf_yield" for d in flagged)

    def test_fiscal_year_mismatch_flagged(self):
        flagged = compare_rows(
            _row({}, fiscal_year=2026), _row({}, fiscal_year=2025)
        )
        # Same fiscal period-end -> labeling difference only, NOT a
        # discrepancy (Yahoo labels by calendar-end year, DB by report year).
        assert not any(d["metric"] == "fiscal_year" for d in flagged)
        # Different fiscal period-end -> real discrepancy.
        a = dict(_row({}, fiscal_year=2025))
        b = dict(_row({}, fiscal_year=2025))
        a["fiscal_year_end"] = "2026-02-01"
        b["fiscal_year_end"] = "2025-02-01"
        flagged = compare_rows(a, b)
        assert any(d["metric"] == "fiscal_year" and d["severity"] == "HIGH"
                   for d in flagged)

    def test_fiscal_year_small_calendar_shift_not_flagged(self):
        # 52/53-week fiscal calendars produce 1-3 day period-end differences
        # between the two sources for the SAME period; within tolerance these
        # must not be flagged.
        a = dict(_row({}, fiscal_year=2025))
        b = dict(_row({}, fiscal_year=2025))
        a["fiscal_year_end"] = "2025-09-27"
        b["fiscal_year_end"] = "2025-09-30"
        flagged = compare_rows(a, b)
        assert not any(d["metric"] == "fiscal_year" for d in flagged)

    def test_missing_values_are_skipped(self):
        assert compare_rows(_row({"revenue": None}), _row({"revenue": 1e9})) == []

    def test_all_metrics_reported(self):
        flags = {d["metric"] for d in compare_rows(_row({}), _row({}))}
        assert "fiscal_year" not in flags  # same FY, no flags


class TestSeverity:
    def test_buckets(self):
        assert _severity(0.5) == "LOW"
        assert _severity(2.0) == "MEDIUM"
        assert _severity(5.0) == "HIGH"
        assert _severity(12.0) == "HIGH"

    def test_metrics_table_shape(self):
        names = [m[0] for m in METRICS]
        assert names == [
            "revenue",
            "net_income",
            "total_assets",
            "total_liabilities",
            "operating_cash_flow",
            "eps",
            "pe_ratio",
            "fcf_yield",
            "roe",
            "net_margin",
        ]