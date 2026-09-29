"""Unit tests for the Graham & Dodd methodology.

Hermetic: fixtures stand in for fundamentals. No network, no database,
no randomness.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Confidence, Verdict
from backend.methodologies.graham_dodd.methodology import GrahamDoddMethodology

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class _Prices:
    """Minimal price stub."""

    def __init__(self, price=100.0):
        self._price = price
        self.calls = []

    def get_current_price(self, ticker):
        self.calls.append(ticker)
        return self._price


def _rows(name):
    """Fixture dicts -> NormalizedFinancials objects."""
    from backend.domain.value_objects.financials_normalized import NormalizedFinancials

    return [
        NormalizedFinancials.from_dict(row)
        for row in json.loads((FIXTURES / name).read_text())
    ]


def _evaluate(fixture, price=100.0):
    methodology = GrahamDoddMethodology()
    return methodology.evaluate("TEST", _rows(fixture), _Prices(price))


# ----------------------------------------------------------------------
# Rule 1 — NWC test
# ----------------------------------------------------------------------


def test_rule_1_nwc_pass():
    """Deep value fixture should PASS rule 1 with a very low price."""
    result = _evaluate("graham_dodd_deep_value.json", price=5.0)
    assert "graham_dodd.rule_1_nwc" in result.passed_rules


def test_rule_1_nwc_fail():
    """Quality fixture should FAIL rule 1 with a high price."""
    result = _evaluate("graham_dodd_quality.json", price=500.0)
    assert "graham_dodd.rule_1_nwc" in result.failed_rules


def test_rule_1_nwc_insufficient():
    """Incomplete fixture has no current assets/liabilities."""
    result = _evaluate("graham_dodd_incomplete.json")
    assert "graham_dodd.rule_1_nwc" not in result.passed_rules
    assert "graham_dodd.rule_1_nwc" not in result.failed_rules


def test_rule_1_nwc_negative_nwc():
    """Negative NWC should return INSUFFICIENT_DATA."""
    result = _evaluate("graham_dodd_weak.json", price=10.0)
    # Weak fixture has current_assets < current_liabilities
    assert "graham_dodd.rule_1_nwc" not in result.passed_rules


# ----------------------------------------------------------------------
# Rule 2 — Fixed-charge coverage
# ----------------------------------------------------------------------


def test_rule_2_coverage_pass():
    """Deep value fixture has strong coverage."""
    result = _evaluate("graham_dodd_deep_value.json")
    assert "graham_dodd.rule_2_fixed_charge_coverage" in result.passed_rules


def test_rule_2_coverage_fail():
    """Weak fixture has poor coverage."""
    result = _evaluate("graham_dodd_weak.json")
    assert "graham_dodd.rule_2_fixed_charge_coverage" in result.failed_rules


def test_rule_2_coverage_insufficient():
    """Incomplete fixture has no interest data."""
    result = _evaluate("graham_dodd_incomplete.json")
    assert "graham_dodd.rule_2_fixed_charge_coverage" not in result.passed_rules
    assert "graham_dodd.rule_2_fixed_charge_coverage" not in result.failed_rules


# ----------------------------------------------------------------------
# Rule 3 — Earnings stability
# ----------------------------------------------------------------------


def test_rule_3_earnings_stability_pass():
    """Deep value fixture has positive earnings — but only 6 years, so INSUFFICIENT_DATA."""
    result = _evaluate("graham_dodd_deep_value.json")
    # Deep value fixture has 6 years, rule_3 needs 10 → INSUFFICIENT_DATA
    assert "graham_dodd.rule_3_earnings_stability" not in result.passed_rules
    assert "graham_dodd.rule_3_earnings_stability" not in result.failed_rules


def test_rule_3_earnings_stability_fail():
    """Weak fixture has negative earnings — but only 6 years, so INSUFFICIENT_DATA."""
    result = _evaluate("graham_dodd_weak.json")
    # Weak fixture has 6 years, rule_3 needs 10 → INSUFFICIENT_DATA
    assert "graham_dodd.rule_3_earnings_stability" not in result.passed_rules
    assert "graham_dodd.rule_3_earnings_stability" not in result.failed_rules


def test_rule_3_earnings_stability_insufficient():
    """Incomplete fixture has only 1 year."""
    result = _evaluate("graham_dodd_incomplete.json")
    assert "graham_dodd.rule_3_earnings_stability" not in result.passed_rules
    assert "graham_dodd.rule_3_earnings_stability" not in result.failed_rules


# ----------------------------------------------------------------------
# Rule 4 — Balance sheet strength
# ----------------------------------------------------------------------


def test_rule_4_balance_sheet_pass():
    """Deep value fixture has strong balance sheet."""
    result = _evaluate("graham_dodd_deep_value.json")
    assert "graham_dodd.rule_4_balance_sheet_strength" in result.passed_rules


def test_rule_4_balance_sheet_fail():
    """Weak fixture has weak balance sheet."""
    result = _evaluate("graham_dodd_weak.json")
    assert "graham_dodd.rule_4_balance_sheet_strength" in result.failed_rules


def test_rule_4_balance_sheet_insufficient():
    """Incomplete fixture has balance sheet data."""
    result = _evaluate("graham_dodd_incomplete.json")
    # Incomplete has total_liabilities=400M, total_assets=800M → 0.5 → PASS
    assert "graham_dodd.rule_4_balance_sheet_strength" in result.passed_rules


# ----------------------------------------------------------------------
# Verdict logic
# ----------------------------------------------------------------------


def test_verdict_buy_with_all_pass():
    """Deep value fixture with low price should be WATCH (rule_3 needs 10 years)."""
    result = _evaluate("graham_dodd_deep_value.json", price=10.0)
    # rule_3 is INSUFFICIENT_DATA (only 6 years), so verdict is WATCH
    assert result.verdict == Verdict.WATCH


def test_verdict_avoid_with_multiple_failures():
    """Weak fixture should be AVOID."""
    result = _evaluate("graham_dodd_weak.json", price=500.0)
    assert result.verdict == Verdict.AVOID


def test_verdict_insufficient_with_many_unknown():
    """Incomplete fixture should be INSUFFICIENT_DATA."""
    result = _evaluate("graham_dodd_incomplete.json")
    assert result.verdict == Verdict.INSUFFICIENT_DATA


# ----------------------------------------------------------------------
# Score
# ----------------------------------------------------------------------


def test_score_is_passed_over_four_times_hundred():
    """Score = passed / 4 × 100."""
    result = _evaluate("graham_dodd_deep_value.json", price=10.0)
    expected = len(result.passed_rules) / 4 * 100
    assert result.score == pytest.approx(expected, abs=0.01)


def test_score_is_none_when_insufficient():
    """Score is None when > 2 rules INSUFFICIENT_DATA."""
    result = _evaluate("graham_dodd_incomplete.json")
    assert result.score is None


# ----------------------------------------------------------------------
# Confidence
# ----------------------------------------------------------------------


def test_confidence_high_when_all_evaluated():
    """Deep value fixture has 3 of 4 rules evaluated (rule_3 needs 10 years)."""
    result = _evaluate("graham_dodd_deep_value.json")
    assert result.confidence == Confidence.MEDIUM


def test_confidence_low_when_many_unknown():
    """Incomplete fixture has many unknown."""
    result = _evaluate("graham_dodd_incomplete.json")
    assert result.confidence == Confidence.LOW


# ----------------------------------------------------------------------
# Red flags
# ----------------------------------------------------------------------


def test_red_flags_listed_for_failures():
    """Weak fixture should have red flags."""
    result = _evaluate("graham_dodd_weak.json", price=500.0)
    assert len(result.red_flags) >= 2


def test_no_red_flags_when_all_pass():
    """Deep value fixture with very low price should have no red flags."""
    result = _evaluate("graham_dodd_deep_value.json", price=5.0)
    # rule_1 PASS (price < 2/3 NWC/share = 5.33), rule_2 PASS, rule_3 N/A, rule_4 PASS
    assert len(result.red_flags) == 0


# ----------------------------------------------------------------------
# Sources
# ----------------------------------------------------------------------


def test_sources_cite_book_and_pages():
    """Every result must cite the book with page numbers."""
    result = _evaluate("graham_dodd_deep_value.json")
    assert result.sources, "every result must cite its sources"
    for ref in result.sources:
        assert ref.book == "Security Analysis"
        assert ref.page, "every source must cite a page"


# ----------------------------------------------------------------------
# Determinism
# ----------------------------------------------------------------------


def test_evaluation_is_deterministic():
    """Same input always produces same output."""
    methodology = GrahamDoddMethodology()
    rows = _rows("graham_dodd_deep_value.json")
    first = methodology.evaluate("TEST", rows, _Prices(10.0))
    second = methodology.evaluate("TEST", rows, _Prices(10.0))
    assert first == second


# ----------------------------------------------------------------------
# Metadata
# ----------------------------------------------------------------------


def test_metadata_reports_book_and_limitations():
    metadata = GrahamDoddMethodology().metadata()
    assert "Security Analysis" in metadata["book"]
    assert metadata["family"] == "DEEP_VALUE"
    assert len(metadata["known_limitations"]) >= 2


def test_rules_expose_all_five():
    methodology = GrahamDoddMethodology()
    ids = {rule.id for rule in methodology.rules()}
    assert ids == {
        "graham_dodd.rule_1_nwc",
        "graham_dodd.rule_2_fixed_charge_coverage",
        "graham_dodd.rule_3_earnings_stability",
        "graham_dodd.rule_4_balance_sheet_strength",
        "graham_dodd.rule_5_margin_of_safety",
    }


# ---------------------------------------------------------------------------
# financial companies (banks/insurers are out of scope for deep value; the
# shared company-type detector guards before any rule runs)
# ---------------------------------------------------------------------------
def test_financial_company_insufficient():
    rows = [
        NormalizedFinancials.from_dict(
            {
                "ticker": "T",
                "fiscal_year": 2024,
                "period": "FY",
                "revenue": 50e9,
                "net_income": 10e9,
                "long_term_debt": 200e9,
                "total_assets": 500e9,
                "total_liabilities": 470e9,
            }
        )
    ]
    result = GrahamDoddMethodology().evaluate("T", rows, _Prices(100.0))
    assert result.verdict == Verdict.INSUFFICIENT_DATA
    assert result.score is None
    assert result.confidence == Confidence.HIGH
    assert result.metrics["financial_company"] is True
    assert result.passed_rules == []
    assert result.failed_rules == []
    assert any("financial" in r.lower() for r in result.reasons)


def test_financial_sector_hint_insufficient():
    rows = [
        NormalizedFinancials.from_dict(
            {
                "ticker": "T",
                "fiscal_year": 2024,
                "period": "FY",
                "revenue": 50e9,
                "net_income": 10e9,
                "sector": "Financial Services",
            }
        )
    ]
    result = GrahamDoddMethodology().evaluate("T", rows, _Prices(100.0))
    assert result.verdict == Verdict.INSUFFICIENT_DATA
    assert result.metrics["financial_company"] is True
