"""Hermetic tests for the FinancialDatabaseRepository reconstruction.

No database, no network, no prices: these tests exercise the pure helpers
``_cumulative_split_multiplier``/``_as_date`` and the in-memory builders
``_normalize_financial_facts``/``_build_normalized_financials``.

Covers the two fixes:
1. R&D gap — the snapshot used to drop ``research_development`` (and the
   sibling income fields) because they were only set on a discarded local
   ``IncomeStatement`` and never carried into ``NormalizedFinancials``.
2. Split adjustment — split ratio facts become a per-row
   ``split_adjustment_factor`` so methodologies can stay hermetic.
"""

from datetime import date

import pytest

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
    _as_date,
    _cumulative_split_multiplier,
)


# ---------------------------------------------------------------------------
# _cumulative_split_multiplier
# ---------------------------------------------------------------------------
def test_no_split_rows_returns_one():
    assert _cumulative_split_multiplier(date(2025, 9, 27), []) == 1.0


def test_none_fy_end_returns_one():
    assert _cumulative_split_multiplier(None, [(date(2020, 8, 28), 4.0)]) == 1.0


def test_split_before_fy_end_is_excluded():
    # 2014-06-06 7:1 predates the FY2015 end -> no adjustment for that year.
    rows = [(date(2014, 6, 6), 7.0)]
    assert _cumulative_split_multiplier(date(2015, 9, 26), rows) == 1.0


def test_split_after_fy_end_multiplies():
    rows = [(date(2020, 8, 28), 4.0)]
    assert _cumulative_split_multiplier(date(2015, 9, 26), rows) == 4.0


def test_multiple_splits_multiply():
    rows = [(date(2014, 6, 6), 7.0), (date(2020, 8, 28), 4.0)]
    assert _cumulative_split_multiplier(date(2013, 9, 28), rows) == 28.0


def test_iso_string_period_end_is_parsed():
    rows = [("2020-08-28", 4.0)]
    assert _cumulative_split_multiplier("2015-09-26", rows) == 4.0


def test_duplicate_split_rows_counted_once():
    # FDB stores the ratio fact once per filing; the same 4:1 split note is
    # re-filed across 10-Ks, so duplicates must NOT multiply the factor again.
    rows = [(date(2020, 8, 28), 4.0), (date(2020, 8, 28), 4.0)]
    assert _cumulative_split_multiplier(date(2015, 9, 26), rows) == 4.0


def test_non_positive_or_missing_ratio_skipped():
    rows = [(date(2020, 8, 28), None), (date(2021, 1, 1), 0.0)]
    assert _cumulative_split_multiplier(date(2015, 9, 26), rows) == 1.0


def test_none_period_end_skipped():
    rows = [(None, 4.0), (date(2020, 8, 28), 2.0)]
    assert _cumulative_split_multiplier(date(2015, 9, 26), rows) == 2.0


def test_reverse_split_divides():
    # 1:10 reverse split -> the ratio is 0.1 and the past as-reported count
    # multiplies by it (5B pre-split shares = 0.5B current), keeping the
    # comparison on today's basis. Fractions are applied, not skipped.
    rows = [(date(2020, 8, 28), 0.1)]
    assert _cumulative_split_multiplier(date(2015, 9, 26), rows) == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# _as_date
# ---------------------------------------------------------------------------
def test_as_date_none_or_garbage_returns_none():
    assert _as_date(None) is None
    assert _as_date("not-a-date") is None


def test_as_date_handles_date_and_iso_string():
    assert _as_date(date(2020, 8, 28)) == date(2020, 8, 28)
    assert _as_date("2020-08-28T00:00:00") == date(2020, 8, 28)


# ---------------------------------------------------------------------------
# _normalize_financial_facts -> income fields
# ---------------------------------------------------------------------------
def _fact(concept, value, year=2024, period="FY", end=None):
    return {
        "concept": concept,
        "value": value,
        "unit": "USD",
        "fiscal_year": year,
        "fiscal_period": period,
        "period_start": date(year, 1, 1),
        "period_end": end or date(year, 12, 31),
    }


def test_normalize_maps_research_and_development_concept():
    income = FinancialDatabaseRepository()._normalize_financial_facts(
        [_fact("ResearchAndDevelopmentExpense", 6_500_000_000)]
    )["income"]
    assert income["research_development"] == 6_500_000_000


def test_normalize_prefers_larger_rnd_tag_when_both_exist():
    # JNJ: the plain tag carries only a residual (0.11B) while the
    # ExcludingAcquiredInProcessCost tag holds the real line (14.67B).
    income = FinancialDatabaseRepository()._normalize_financial_facts(
        [
            _fact("ResearchAndDevelopmentExpense", 110_000_000),
            _fact(
                "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
                14_670_000_000,
            ),
        ]
    )["income"]
    assert income["research_development"] == 14_670_000_000


def test_normalize_keeps_plain_rnd_tag_when_it_dominates():
    # Both tags complete (AIP small): the plain value is the more inclusive
    # line and must not be clobbered by the Excluding tag.
    income = FinancialDatabaseRepository()._normalize_financial_facts(
        [
            _fact("ResearchAndDevelopmentExpense", 18_000_000_000),
            _fact(
                "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
                17_500_000_000,
            ),
        ]
    )["income"]
    assert income["research_development"] == 18_000_000_000


def test_normalize_maps_excluding_tag_on_its_own():
    income = FinancialDatabaseRepository()._normalize_financial_facts(
        [
            _fact(
                "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
                9_000_000_000,
            )
        ]
    )["income"]
    assert income["research_development"] == 9_000_000_000


def test_normalize_maps_sga_and_operating_expense():
    income = FinancialDatabaseRepository()._normalize_financial_facts(
        [
            _fact("SellingGeneralAndAdministrativeExpense", 8_000_000_000),
            _fact("OperatingExpenses", 21_000_000_000),
            _fact("NonoperatingIncomeExpense", 400_000_000),
        ]
    )["income"]
    assert income["sga"] == 8_000_000_000
    assert income["operating_expense"] == 21_000_000_000
    assert income["non_operating_income_expense"] == 400_000_000


def test_normalize_unknown_concept_ignored():
    income = FinancialDatabaseRepository()._normalize_financial_facts(
        [_fact("TotallyUnknownConcept", 123)]
    )["income"]
    assert income == {}


# ---------------------------------------------------------------------------
# _build_normalized_financials carries the income fields and split factor
# ---------------------------------------------------------------------------
def _statements(**overrides):
    base = {
        "income": {
            "revenue": 100_000_000_000,
            "research_development": 6_500_000_000,
            "sga": 8_000_000_000,
            "operating_expense": 21_000_000_000,
            "non_operating_income_expense": 400_000_000,
        },
        "balance": {"shares_outstanding": 14_900_000_000},
        "cash_flow": {},
    }
    base.update(overrides)
    return base


def test_build_normalized_carries_research_development():
    repo = FinancialDatabaseRepository()
    fin = repo._build_normalized_financials("AAPL", 2025, _statements())
    assert fin.research_development == 6_500_000_000
    assert fin.sga == 8_000_000_000
    assert fin.operating_expense == 21_000_000_000
    assert fin.non_operating_income_expense == 400_000_000
    assert fin.revenue == 100_000_000_000


def test_build_normalized_carries_split_factor():
    repo = FinancialDatabaseRepository()
    fin = repo._build_normalized_financials(
        "AAPL", 2015, _statements(), split_adjustment_factor=4.0
    )
    assert fin.split_adjustment_factor == 4.0


def test_build_normalized_split_factor_defaults_to_one():
    repo = FinancialDatabaseRepository()
    fin = repo._build_normalized_financials("AAPL", 2015, _statements())
    assert fin.split_adjustment_factor == 1.0


def test_build_normalized_missing_fields_stay_none_not_aborted():
    repo = FinancialDatabaseRepository()
    fin = repo._build_normalized_financials(
        "TEST",
        2024,
        {"income": {"revenue": 10.0}, "balance": {}, "cash_flow": {}},
    )
    assert fin.revenue == 10.0
    assert fin.research_development is None
    assert fin.shares_outstanding is None
