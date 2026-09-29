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
import os
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.providers.yahoo.provider import YahooFinanceProvider
from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))
from validate_sp500 import (
    METRICS,
    _load_exclusions,
    _match_exclusion,
    _severity,
    compare_rows,
)


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

    def test_annual_fact_wins_over_later_quarter_retagged_fy(self):
        # Salesforce (Jan-31 fiscal year): the FY2014 10-K supplemental
        # quarterly table retags Q1-Q3 FY2014 (period_ends Apr/Jul/Oct 2013)
        # as 'FY'. After calendar-year bucketing those land in the FY2013
        # bucket with a LATER period_end than the real annual figure
        # (2013-01-31). The ANNUAL period span must win the dedup instead of
        # the newest period_end.
        facts = [
            _fact("RevenueFromContractWithCustomerExcludingAssessedTax",
                  0.853e9, date(2013, 4, 30), period_start=date(2013, 2, 1)),
            _fact("RevenueFromContractWithCustomerExcludingAssessedTax",
                  2.925e9, date(2013, 10, 31), period_start=date(2013, 2, 1)),
            _fact("RevenueFromContractWithCustomerExcludingAssessedTax",
                  3.050195e9, date(2013, 1, 31), period_start=date(2012, 2, 1)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["revenue"] == 3.050195e9

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

    def test_operating_income_loss_populates_operating_income_and_ebit(self):
        # OperatingIncomeLoss is the operating-income tag most filers use and
        # must populate BOTH operating_income (for operating margin) and ebit
        # (for EV/EBIT, ROIC). It must not be shadowed into only one field by
        # a duplicate dict key.
        facts = [
            _fact("OperatingIncomeLoss", 2.026e9, date(2025, 12, 31)),
            _fact("Revenues", 8.799e9, date(2025, 12, 31)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["operating_income"] == 2.026e9
        assert normalized["income"]["ebit"] == 2.026e9

    def test_explicit_ebit_wins_over_operating_income_fallback(self):
        # A filer that reports both keeps its own EBIT figure; operating income
        # stays available on its own field.
        facts = [
            _fact("OperatingIncomeLoss", 2.5e9, date(2025, 12, 31)),
            _fact("EBIT", 2.2e9, date(2025, 12, 31)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["operating_income"] == 2.5e9
        assert normalized["income"]["ebit"] == 2.2e9

    def test_bucket_year_filter_drops_neighbour_year_facts(self):
        # A fiscal-year bucket can hold next year's facts (a sync tagged the
        # same filing under two fiscal_years). With bucket_year given, the
        # next-year value must not win the newest-period_end dedup, and the
        # as-of-date cover-page fact must not lift max period_end for total
        # debt.
        facts = [
            _fact("Revenues", 37.895e9, date(2025, 1, 31)),
            _fact("Revenues", 41.525e9, date(2026, 1, 31)),  # next year
            _fact("LongTermDebt", 30e9, date(2025, 1, 31)),
            _fact(
                "EntityCommonStockSharesOutstanding",
                950e6,
                date(2026, 2, 20),  # as-of cover-page fact
            ),
            _fact("LongTermDebt", 32e9, date(2026, 1, 31)),  # next year
        ]
        normalized = self._repo._normalize_financial_facts(facts, bucket_year=2025)
        assert normalized["income"]["revenue"] == 37.895e9
        assert normalized["balance"]["total_debt"] == 30e9

    def test_bucket_year_filter_falls_back_when_no_row_matches(self):
        # When no row has a period_end within the labelled year (unusual label
        # scheme), the bucket is normalized unfiltered rather than emptied.
        facts = [
            _fact("Revenues", 100e9, date(2026, 1, 31)),
            _fact("NetIncomeLoss", 10e9, date(2026, 1, 31)),
        ]
        normalized = self._repo._normalize_financial_facts(facts, bucket_year=2025)
        assert normalized["income"]["revenue"] == 100e9

    def test_total_debt_no_double_count_of_alias_concepts(self):
        # Newmont reports LongTermDebt and LongTermDebtNoncurrent with the same
        # value (aliases of one non-current portion). Only a single preferred
        # tag per portion may count, otherwise total debt is overstated 2x.
        facts = [
            _fact("LongTermDebt", 5.115e9, date(2025, 12, 31)),
            _fact("LongTermDebtNoncurrent", 5.115e9, date(2025, 12, 31)),
            _fact("CashAndCashEquivalents", 1e9, date(2025, 12, 31)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["balance"]["total_debt"] == 5.115e9

    def test_total_debt_sums_current_and_noncurrent_portions(self):
        # A filer with separate current and non-current tags gets both summed…
        facts = [
            _fact("DebtCurrent", 1.0e9, date(2025, 12, 31)),
            _fact("LongTermDebtAndCapitalLeaseObligations", 18.7e9, date(2025, 12, 31)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["balance"]["total_debt"] == 19.7e9

        # …while a filer that reports the same non-current debt under several
        # tags (D's LongTermDebt + LongTermDebtAndCapitalLeaseObligations) keeps
        # only the preferred one, plus its short-term borrowings.
        facts = [
            _fact("LongTermDebt", 46.33e9, date(2025, 12, 31)),
            _fact("LongTermDebtAndCapitalLeaseObligations", 44.08e9, date(2025, 12, 31)),
            _fact("ShortTermBorrowings", 2.46e9, date(2025, 12, 31)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["balance"]["total_debt"] == 44.08e9 + 2.46e9

    def test_total_debt_max_pe_scoped_to_balance_facts(self):
        # An as-of cover-page fact with a later period_end must not push the
        # balance snapshot to an empty bucket, or total debt would be dropped.
        facts = [
            _fact("LongTermDebt", 8.5e9, date(2025, 9, 30)),
            _fact("EntityPublicFloat", 400e6, date(2025, 11, 15)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["balance"]["total_debt"] == 8.5e9

    def test_cash_falls_back_to_restricted_inclusive_concept(self):
        # BEN reports cash only under the restricted-inclusive tag; it must
        # still land in cash_and_equivalents when the standard tags are absent.
        facts = [
            _fact(
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                3.57e9,
                date(2025, 9, 30),
            ),
            _fact("LongTermDebt", 2.36e9, date(2025, 9, 30)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["balance"]["cash_and_equivalents"] == 3.57e9
        assert normalized["balance"]["total_debt"] == 2.36e9

    def test_depreciation_prefers_complete_add_back_over_partial_tag(self):
        # A filer reporting both the generic D&A add-back and a partial
        # COGS-only tag keeps the complete figure.
        facts = [
            _fact("DepreciationAndAmortization", 1.5e9, date(2025, 12, 31)),
            _fact(
                "CostOfGoodsSoldDepreciationDepletionAndAmortization",
                0.4e9,
                date(2025, 12, 31),
            ),
            _fact("NetCashProvidedByUsedInOperatingActivities", 2e9, date(2025, 12, 31)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["cash_flow"]["depreciation_amortization"] == 1.5e9

    def test_depreciation_falls_back_to_utilities_add_back(self):
        # AEE files D&A only as DepreciationAmortizationAndAccretionNet; it
        # must still populate the field.
        facts = [
            _fact("DepreciationAmortizationAndAccretionNet", 1.524e9, date(2025, 12, 31)),
            _fact("NetCashProvidedByUsedInOperatingActivities", 2.2e9, date(2025, 12, 31)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["cash_flow"]["depreciation_amortization"] == 1.524e9

    def test_depreciation_falls_back_to_depreciation_tag(self):
        # PWR files D&A only as Depreciation (capital-intensive contractor).
        facts = [
            _fact("Depreciation", 359.363e6, date(2025, 12, 31)),
            _fact("NetCashProvidedByUsedInOperatingActivities", 1e9, date(2025, 12, 31)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["cash_flow"]["depreciation_amortization"] == 359.363e6

    def test_operating_cash_flow_falls_back_to_continuing_operations(self):
        # JCI tags OCF only as NetCashProvidedByUsedInOperatingActivities
        # ContinuingOperations (it divested its residential HVAC business);
        # the variant must still populate operating_cash_flow.
        facts = [
            _fact(
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
                2.554e9, date(2025, 12, 31),
            ),
            _fact(
                "CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations",
                -1.155e9, date(2025, 12, 31),
            ),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["cash_flow"]["operating_cash_flow"] == 2.554e9

    def test_operating_cash_flow_prefers_plain_tag_when_both_filed(self):
        # A filer with both tags (plain total + continuing-only variant) keeps
        # the plain figure; the variant is only a fallback.
        facts = [
            _fact("NetCashProvidedByUsedInOperatingActivities", 12e9, date(2025, 12, 31)),
            _fact(
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
                10e9, date(2025, 12, 31),
            ),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["cash_flow"]["operating_cash_flow"] == 12e9


class TestFiscalYearEndMode:
    """get_fiscal_year_end_date must return the bucket's OWN fiscal year end:
    one-off facts tagged 'FY' (fee schedules, Entity% cover-page rows) must not
    shift it, the quarterly rows of a 10-K supplemental table retagged 'FY'
    must not hijack it, and — critically — an OLDER comparative with a LONGER
    annual span that a sync mislabelled under the current fiscal_year must not
    win over the bucket's own calendar-year facts."""

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
        # The query must anchor on the mapped statement concepts (not Entity%
        # cover-page facts or one-off disclosures), rank the facts whose
        # period_end falls in the bucket's OWN calendar year first (so a
        # longer-span prior comparative mislabelled into the bucket cannot
        # win), then prefer the LONGEST annual period so 10-K supplemental
        # quarterly rows retagged 'FY' (which land in the previous bucket with
        # a later period_end for a Jan-31 fiscal-year-end filer) cannot shift
        # the year end either.
        sql = executed[-1]
        assert "concept = ANY" in sql
        assert "Entity" not in sql
        assert "period_end - COALESCE(f.period_start, f.period_end" in sql
        assert "LIMIT 1" in sql
        # The calendar-year-match ranking must come BEFORE the span ranking.
        assert "EXTRACT(YEAR FROM f.period_end)" in sql
        assert sql.index("EXTRACT(YEAR FROM f.period_end)") < sql.index(
            "period_end - COALESCE(f.period_start, f.period_end"
        )

    def test_prefers_bucket_calendar_year_over_longer_prior_comparative(
        self, monkeypatch
    ):
        """AAPL-style pollution: the bucket holds an older comparative with a
        LONGER annual span (FY2023, 370 days) than its own facts (363 days).
        The calendar-year match must win — not the longest span."""
        repo = FinancialDatabaseRepository()

        executed: list[str] = []
        captured_params: list[tuple] = []

        # AAPL FY2025 bucket rows: own fiscal-year facts (period_end 2025-09-27,
        # span 363), the FY2024 comparative (2024-09-28, span 363) and a
        # mislabelled FY2023 comparative (2023-09-30, span 370). Under the old
        # span-first ordering the 370-day comparative hijacked every year.
        rows = [
            {"period_end": date(2025, 9, 27), "span": 363},
            {"period_end": date(2024, 9, 28), "span": 363},
            {"period_end": date(2023, 9, 30), "span": 370},
        ]

        class FakeCursor:
            def execute(self, sql, par):
                executed.append(sql)
                captured_params.append(par)
                fiscal_year = int(par[1])
                # Simulate the SQL ranking: calendar-year match first, then
                # period span, then period_end.
                self._result = sorted(
                    rows,
                    key=lambda r: (
                        r["period_end"].year == fiscal_year,
                        r["span"],
                        r["period_end"],
                    ),
                    reverse=True,
                )[0]

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

        # The bucket's own fiscal year end wins over the longer-span mislabelled
        # comparative.
        assert repo.get_fiscal_year_end_date("AAPL", 2025) == date(2025, 9, 27)
        # A polluted 2024 bucket must equally yield its own calendar-year end.
        assert repo.get_fiscal_year_end_date("AAPL", 2024) == date(2024, 9, 28)


class TestSharesOutstandingPreference:
    """EPS must be computed on a diluted, weighted-average share basis, and
    duplicate share rows for the same fiscal-year end must be resolved
    deterministically:

    * a *scale* duplicate (legacy thousands-tagged, ratio >= 10x) picks the
      larger, correct value (Ball 2009/2010);
    * a *split-restatement* duplicate (small ratio, e.g. the ~2x restatement
      of Ball 2015/2016 after its 2017 2:1 split) keeps the ORIGINAL
      earliest-filed disclosure, because PriceService's split adjustment
      already carries the count onto the current basis — combining both would
      double-count the split;
    * implausibly small counts with no anchor degrade to None.
    """

    @staticmethod
    def _make_repo(monkeypatch, queue):
        repo = FinancialDatabaseRepository()
        executed: list[str] = []
        params: list[tuple] = []

        class FakeCursor:
            def __init__(self):
                self._rows: list[dict] = []

            def execute(self, sql, par):
                executed.append(sql)
                params.append(par)
                self._rows = queue.pop(0)

            def fetchall(self):
                return self._rows

            def fetchone(self):
                return self._rows[0] if self._rows else None

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
        return repo, executed, params

    @staticmethod
    def _row(value, period_end=date(2025, 12, 31), filing_date=date(2026, 2, 1)):
        return {"value": value, "period_end": period_end, "filing_date": filing_date}

    def test_prefer_diluted_queries_weighted_average_concept(self, monkeypatch):
        repo, executed, params = self._make_repo(monkeypatch, [
            [self._row("466733000")],   # diluted weighted-average
            [self._row("469000000")],   # cover-page anchor
        ])
        result = repo.get_shares_outstanding("BF-B", 2026, prefer_diluted=True)
        assert result == 466733000.0
        # The diluted weighted-average concept must be tried first.
        assert params and "WeightedAverageNumber" in params[0][2]

    def test_default_preference_starts_with_end_of_period(self, monkeypatch):
        repo, executed, params = self._make_repo(monkeypatch, [
            [self._row("466335000")],   # CommonStockSharesOutstanding
            [self._row("470000000")],   # cover-page anchor
        ])
        repo.get_shares_outstanding("BF-B", 2026)
        assert params and params[0][2] == "CommonStockSharesOutstanding"

    def test_legacy_thousands_duplicates_pick_larger(self, monkeypatch):
        # Ball 2009 carries BOTH the thousands-tagged (187,572, filed in the
        # FY2009 10-K) and the correct (187,572,000, filed a year later) rows
        # for the same period_end. The ratio (1000x) identifies the scale
        # duplicate and the larger, correct value must win deterministically.
        repo, executed, _ = self._make_repo(monkeypatch, [
            [],  # CommonStockSharesOutstanding: not filed
            [
                self._row("187572", date(2009, 12, 31), date(2010, 2, 2)),
                self._row("187572000", date(2009, 12, 31), date(2011, 2, 1)),
            ],
            [],  # EntityCommonStockSharesOutstanding anchor: absent
        ])
        result = repo.get_shares_outstanding("BALL", 2009)
        assert result == 187572000.0
        # The candidate query must fetch up to two rows per period_end,
        # earliest-filed first, so the duplicate resolver can compare them.
        assert "filing_date ASC NULLS LAST" in executed[1]

    def test_split_restatement_keeps_original_disclosure(self, monkeypatch):
        # Ball 2015/2016 were restated ~2x by the post-2017-split 10-K. That
        # small-ratio duplicate must NOT win: PriceService already applies the
        # 2:1 split adjustment to the as-reported count, so picking the
        # restated value would double-count the split and halve EPS.
        repo, executed, _ = self._make_repo(monkeypatch, [
            [],  # CommonStockSharesOutstanding: not filed
            [
                self._row("137300000", date(2015, 12, 31), date(2016, 2, 16)),
                self._row("274600000", date(2015, 12, 31), date(2018, 3, 1)),
            ],
            [],  # EntityCommonStockSharesOutstanding anchor: absent
        ])
        result = repo.get_shares_outstanding("BALL", 2015)
        assert result == 137300000.0

    def test_repairs_legacy_thousands_scaled_shares(self, monkeypatch):
        # Ball 2010: the weighted-average basic share count was filed in
        # thousands (180,746). The 1000x duplicate and the cover-page anchor
        # (169,198,602) both resolve to the correct 180,746,000.
        repo, _, _ = self._make_repo(monkeypatch, [
            [],  # CommonStockSharesOutstanding: not filed
            [
                self._row("180746", date(2010, 12, 31), date(2011, 2, 1)),
                self._row("180746000", date(2010, 12, 31), date(2012, 2, 1)),
            ],
            [self._row("169198602", date(2010, 12, 31), date(2011, 2, 1))],
        ])
        result = repo.get_shares_outstanding("BALL", 2010)
        assert result == 180746000.0

    def test_no_rescale_when_counts_are_close(self, monkeypatch):
        # A legitimate weighted-average / outstanding pair must be untouched.
        repo, _, _ = self._make_repo(monkeypatch, [
            [self._row("466733000")],   # diluted weighted-average
            [self._row("469000000")],   # cover-page anchor
        ])
        result = repo.get_shares_outstanding("CRM", 2026, prefer_diluted=True)
        assert result == 466733000.0

    def test_implausibly_small_shares_return_none(self, monkeypatch):
        # Ball 2008: only the thousands-tagged weighted-average rows exist and
        # there is no cover-page anchor to repair against. A sub-1M share
        # count is unusable for per-share metrics, so None must be returned
        # instead of a ~1000x-inflated EPS.
        repo, _, _ = self._make_repo(monkeypatch, [
            [],  # CommonStockSharesOutstanding: not filed
            [self._row("191714", date(2008, 12, 31), date(2009, 2, 2))],
            [],  # EntityCommonStockSharesOutstanding anchor: absent
        ])
        result = repo.get_shares_outstanding("BALL", 2008)
        assert result is None


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


class TestOperatingLeaseLeaseIncomePreference:
    """OperatingLeaseLeaseIncome must only carry revenue for REIT-like filers
    whose rental income is the whole top line, and must never shadow a genuine
    contract-revenue figure (e.g. DD 6.85B sales vs 74M side rental)."""

    _repo = FinancialDatabaseRepository()

    def test_contract_revenue_wins_over_small_rental_income(self):
        facts = [
            _fact("OperatingLeaseLeaseIncome", 74e6, date(2025, 12, 31)),
            _fact(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                6.849e9,
                date(2025, 12, 31),
                period_start=date(2025, 1, 1),
            ),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["revenue"] == 6.849e9

    def test_dominant_rental_income_wins_over_partial_contract_tag(self):
        # CPT: no explicit revenue tag; the contract-revenue figure is a 13M
        # leftover while rental income (1.57B) is the whole top line.
        facts = [
            _fact(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                12.967e6,
                date(2025, 12, 31),
                period_start=date(2025, 1, 1),
            ),
            _fact("OperatingLeaseLeaseIncome", 1.573544e9, date(2025, 12, 31)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["revenue"] == 1.573544e9

    def test_rental_income_used_when_no_other_revenue_tag(self):
        facts = [_fact("OperatingLeaseLeaseIncome", 1.573544e9, date(2025, 12, 31))]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["revenue"] == 1.573544e9


class TestBankRevenueOverride:
    """Banks/brokers that present a net-of-interest top line must sum
    InterestIncomeExpenseNet + NoninterestIncome when both are present,
    even if a small contract-revenue tag is also filed."""

    _repo = FinancialDatabaseRepository()

    def test_bank_pair_sums_to_revenue(self):
        facts = [
            _fact("InterestIncomeExpenseNet", 6.948e9, date(2025, 12, 31)),
            _fact("NoninterestIncome", 2.742e9, date(2025, 12, 31)),
            _fact(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                2.2e9, date(2025, 12, 31),
                period_start=date(2025, 1, 1),
            ),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["revenue"] == 9.690e9

    def test_single_bank_component_does_not_trigger_override(self):
        facts = [_fact("InterestIncomeExpenseNet", 6.948e9, date(2025, 12, 31))]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"].get("revenue") is None


class TestCapexFieldPriority:
    """Capital expenditure must prefer the as-filed payments-to-acquire-plants
    tag, then the segment expenditure tag.  Preferring PaymentsToAcquire
    ProductiveAssets (which mixes in assets acquired in one-off transactions)
    understated e.g. AEP's construction-heavy capex."""

    _repo = FinancialDatabaseRepository()

    def test_payments_to_acquire_ppe_preferred_over_segment(self):
        facts = [
            _fact("PaymentsToAcquirePropertyPlantAndEquipment", 5e9, date(2025, 12, 31)),
            _fact("SegmentExpenditureAdditionToLongLivedAssets", 3e9, date(2025, 12, 31)),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["cash_flow"]["capital_expenditure"] == 5e9

    def test_segment_preferred_over_payments_to_acquire_productive_assets(self):
        # AEP: PaymentsToAcquireProductiveAssets (2.9B) was chosen before; the
        # 10-K capex (11.9B) is SegmentExpenditureAdditionToLongLivedAssets.
        facts = [
            _fact("PaymentsToAcquireProductiveAssets", 2.924e9, date(2025, 12, 31)),
            _fact(
                "SegmentExpenditureAdditionToLongLivedAssets",
                11.906e9, date(2025, 12, 31),
            ),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["cash_flow"]["capital_expenditure"] == 11.906e9


class TestDilutedNetIncomeFYEAnchoring:
    """get_available_to_common_diluted_net_income must restrict to the
    fiscal-year-end period_end.  Otherwise a comparative prior-year column
    tagged FY under the wrong fiscal_year (APA: 804M, period_end 2024-12-31
    under fiscal_year 2025) is picked up and corrupts EPS."""

    _repo = FinancialDatabaseRepository()

    def test_ignore_comparative_column_mislabeled_under_fiscal_year(self, monkeypatch):
        repo = FinancialDatabaseRepository()
        executed: list[str] = []

        q = iter([
            # anchor subquery -> FYE for "APA"
            {"period_end": "2025-12-31"},
            # the outer query finds nothing for 2025-12-31 diluted NI
        ])

        class FakeCursor:
            def execute(self, sql, par):
                executed.append(sql)
                self._result = next(q)

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
        # A comparative column mislabeled under fiscal_year=2025 (period_end
        # 2024-12-31) must be EXCLUDED by the period_end anchor.
        result = repo.get_available_to_common_diluted_net_income("APA", 2025)
        assert result is None
        sql = executed[-1]
        assert "period_end = (" in sql
        assert "MAX(f2.period_end)" in sql

    def test_fye_diluted_net_income_kept(self):
        facts = [
            _fact(
                "NetIncomeLossAvailableToCommonStockholdersDiluted",
                1895e6,
                date(2025, 12, 31),
            ),
        ]
        normalized = self._repo._normalize_financial_facts(facts)
        assert normalized["income"]["net_income"] == 1895e6


class TestExclusionLoaderAndMatcher:
    """config/validation_exclusions.yaml parsing and (ticker, metric) matching,
    including the '*' metric wildcard."""

    def _yaml(self, tmp_path, text: str):
        p = tmp_path / "exclusions.yaml"
        p.write_text(text)
        return p

    def test_loads_rules_and_strips_comments(self, tmp_path):
        p = self._yaml(
            tmp_path,
            "\n".join(
                [
                    "# header comment",
                    "validation_exclusions:",
                    "  - ticker: ABNB",
                    "    metric: eps",
                    "    classification: EXTERNAL_SOURCE_ERROR",
                    "    reason: \"foo\"",
                    "  - ticker: HAS",
                    "    metric: revenue",
                    "    classification: EXPECTED_DIFFERENCE",
                    "    reason: gross vs net",
                    "",
                ]
            ),
        )
        rules = _load_exclusions(p)
        assert len(rules) == 2
        assert rules[0] == {
            "ticker": "ABNB",
            "metric": "eps",
            "classification": "EXTERNAL_SOURCE_ERROR",
            "reason": "foo",
        }
        assert rules[1]["ticker"] == "HAS"

    def test_missing_file_returns_empty(self, tmp_path):
        assert _load_exclusions(tmp_path / "nope.yaml") == []

    def test_match_exact(self):
        rules = [{"ticker": "ABNB", "metric": "eps", "classification": "X"}]
        match = _match_exclusion({"ticker": "ABNB", "metric": "eps"}, rules)
        assert match and match["classification"] == "X"
        assert _match_exclusion({"ticker": "ABNB", "metric": "pe_ratio"}, rules) is None
        assert _match_exclusion({"ticker": "Z", "metric": "eps"}, rules) is None

    def test_match_metric_wildcard(self):
        rules = [{"ticker": "HAS", "metric": "*", "classification": "X"}]
        assert _match_exclusion({"ticker": "HAS", "metric": "revenue"}, rules)
        assert _match_exclusion({"ticker": "HAS", "metric": "net_income"}, rules)
        assert _match_exclusion({"ticker": "OTHER", "metric": "revenue"}, rules) is None

    def test_real_exclusions_file_parses(self):
        rules = _load_exclusions(Path("config") / "validation_exclusions.yaml")
        assert len(rules) == 22
        assert all(r.get("ticker") and r.get("metric") and r.get("classification")
                   for r in rules)
        assert _match_exclusion({"ticker": "LNT", "metric": "fcf_yield"}, rules)