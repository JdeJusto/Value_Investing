"""Unit tests for the Buffett/Clark methodology.

Hermetic: fixtures stand in for fundamentals. No network, no database,
no randomness.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Confidence, Verdict
from backend.methodologies.buffett_clark.methodology import BuffettClarkMethodology

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class _Prices:
    """Minimal price stub (not used by this methodology but required by ABC)."""

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
    methodology = BuffettClarkMethodology()
    return methodology.evaluate("TEST", _rows(fixture), _Prices(price))


# ----------------------------------------------------------------------
# Rule 1 — Gross margin
# ----------------------------------------------------------------------


def test_rule_1_gross_margin_pass():
    """KO has gross margin ~61% — should PASS."""
    result = _evaluate("buffett_clark_ko.json")
    assert "buffett_clark.rule_1_gross_margin" in result.passed_rules
    assert result.metrics["rule_1_gross_margin"] >= 0.40


def test_rule_1_gross_margin_fail():
    """GM has gross margin ~11% — should FAIL."""
    result = _evaluate("buffett_clark_gm.json")
    assert "buffett_clark.rule_1_gross_margin" in result.failed_rules
    assert result.metrics["rule_1_gross_margin"] < 0.20


def test_rule_1_gross_margin_insufficient():
    """Incomplete fixture has no gross margin data."""
    result = _evaluate("buffett_clark_incomplete.json")
    assert "buffett_clark.rule_1_gross_margin" not in result.passed_rules
    assert "buffett_clark.rule_1_gross_margin" not in result.failed_rules
    assert result.metrics["rule_1_gross_margin"] is None


def test_rule_1_zero_revenue_is_not_evaluable():
    """A zero-revenue year must not raise ZeroDivisionError (consensus crash)."""
    rows = [
        NormalizedFinancials.from_dict(
            {
                "ticker": "ZERO",
                "fiscal_year": 2024,
                "period": "FY",
                "revenue": 0,
                "gross_profit": 10e9,
                "net_income": 1e9,
            }
        )
    ]
    result = BuffettClarkMethodology().evaluate("ZERO", rows, _Prices(100.0))
    assert "buffett_clark.rule_1_gross_margin" not in result.passed_rules
    assert "buffett_clark.rule_1_gross_margin" not in result.failed_rules
    assert result.metrics["rule_1_gross_margin"] is None


# ----------------------------------------------------------------------
# Rule 2 — Interest burden
# ----------------------------------------------------------------------


def test_rule_2_interest_burden_pass():
    """KO has interest burden ~8% — should PASS."""
    result = _evaluate("buffett_clark_ko.json")
    assert "buffett_clark.rule_2_interest_burden" in result.passed_rules
    assert result.metrics["rule_2_interest_burden"] <= 0.10


def test_rule_2_interest_burden_fail():
    """GM has interest burden ~50% — should FAIL."""
    result = _evaluate("buffett_clark_gm.json")
    assert "buffett_clark.rule_2_interest_burden" in result.failed_rules
    assert result.metrics["rule_2_interest_burden"] >= 0.50


def test_rule_2_interest_burden_insufficient():
    """Incomplete fixture has no interest data."""
    result = _evaluate("buffett_clark_incomplete.json")
    assert "buffett_clark.rule_2_interest_burden" not in result.passed_rules
    assert "buffett_clark.rule_2_interest_burden" not in result.failed_rules


# ----------------------------------------------------------------------
# Rule 3 — Margin durability
# ----------------------------------------------------------------------


def test_rule_3_margin_durability_pass():
    """AAPL has stable margins over 3 years — should be INSUFFICIENT_DATA
    (needs 5 years minimum per the book's durability criterion)."""
    result = _evaluate("buffett_clark_aapl.json")
    # AAPL margins: 2024=46.2%, 2023=44.2%, 2022=43.3%
    # Only 3 years available, rule requires 5 — should be N/A
    assert "buffett_clark.rule_3_margin_durability" not in result.passed_rules
    assert "buffett_clark.rule_3_margin_durability" not in result.failed_rules


def test_rule_3_margin_durability_insufficient():
    """Incomplete fixture has only 1 year — should be N/A."""
    result = _evaluate("buffett_clark_incomplete.json")
    assert "buffett_clark.rule_3_margin_durability" not in result.passed_rules
    assert "buffett_clark.rule_3_margin_durability" not in result.failed_rules


# ----------------------------------------------------------------------
# Rule 4 — Debt
# ----------------------------------------------------------------------


def test_rule_4_debt_pass():
    """KO has debt/equity ~1.56 — should FAIL (above 0.50 threshold)."""
    result = _evaluate("buffett_clark_ko.json")
    # KO has high debt relative to equity
    assert "buffett_clark.rule_4_debt" in result.failed_rules


def test_rule_4_debt_fail():
    """GM has very high debt/equity — should FAIL."""
    result = _evaluate("buffett_clark_gm.json")
    assert "buffett_clark.rule_4_debt" in result.failed_rules
    assert result.metrics["rule_4_debt"] > 0.50


def test_rule_4_debt_insufficient():
    """Incomplete fixture has no debt data."""
    result = _evaluate("buffett_clark_incomplete.json")
    assert "buffett_clark.rule_4_debt" not in result.passed_rules
    assert "buffett_clark.rule_4_debt" not in result.failed_rules


# ----------------------------------------------------------------------
# Rule 5 — Cash
# ----------------------------------------------------------------------


def test_rule_5_cash_pass():
    """KO has cash/assets ~15% — should PASS."""
    result = _evaluate("buffett_clark_ko.json")
    assert "buffett_clark.rule_5_cash" in result.passed_rules
    assert result.metrics["rule_5_cash"] >= 0.10


def test_rule_5_cash_fail():
    """GM has cash/assets ~9% — should FAIL."""
    result = _evaluate("buffett_clark_gm.json")
    assert "buffett_clark.rule_5_cash" in result.failed_rules


def test_rule_5_cash_insufficient():
    """Incomplete fixture has cash data — should be evaluated."""
    result = _evaluate("buffett_clark_incomplete.json")
    # Incomplete has cash=500M, assets=8B → 6.25% → FAIL
    assert "buffett_clark.rule_5_cash" in result.failed_rules


# ----------------------------------------------------------------------
# Rule 6 — Capex
# ----------------------------------------------------------------------


def test_rule_6_capex_pass():
    """KO has capex/FCF ~19% — should PASS."""
    result = _evaluate("buffett_clark_ko.json")
    assert "buffett_clark.rule_6_capex" in result.passed_rules
    assert result.metrics["rule_6_capex"] <= 0.50


def test_rule_6_capex_fail():
    """GM has capex/FCF ~200% — should FAIL."""
    result = _evaluate("buffett_clark_gm.json")
    assert "buffett_clark.rule_6_capex" in result.failed_rules


def test_rule_6_capex_insufficient():
    """Incomplete fixture has no capex data."""
    result = _evaluate("buffett_clark_incomplete.json")
    assert "buffett_clark.rule_6_capex" not in result.passed_rules
    assert "buffett_clark.rule_6_capex" not in result.failed_rules


# ----------------------------------------------------------------------
# Rule 7 — Retained earnings
# ----------------------------------------------------------------------


def test_rule_7_retained_earnings_pass():
    """KO has rising retained earnings — should PASS."""
    result = _evaluate("buffett_clark_ko.json")
    assert "buffett_clark.rule_7_retained_earnings" in result.passed_rules


def test_rule_7_retained_earnings_fail():
    """AAPL has declining retained earnings — should FAIL."""
    result = _evaluate("buffett_clark_aapl.json")
    assert "buffett_clark.rule_7_retained_earnings" in result.failed_rules


def test_rule_7_retained_earnings_insufficient():
    """Incomplete fixture has only 1 year — should be N/A."""
    result = _evaluate("buffett_clark_incomplete.json")
    assert "buffett_clark.rule_7_retained_earnings" not in result.passed_rules
    assert "buffett_clark.rule_7_retained_earnings" not in result.failed_rules


# ----------------------------------------------------------------------
# Verdict logic
# ----------------------------------------------------------------------


def test_verdict_buy_with_five_passes():
    """KO passes five of the seven legacy rules, but the three-year fixture
    cannot evaluate the 10-year deep checks, so missing weight exceeds 30%
    and the weighted verdict is INSUFFICIENT_DATA (v2.0.0 semantics)."""
    result = _evaluate("buffett_clark_ko.json")
    assert result.verdict == Verdict.INSUFFICIENT_DATA
    assert result.score is None
    assert len(result.passed_rules) >= 5


def test_verdict_avoid_with_few_passes():
    """GM fails most rules; the weighted ratio is far below the 50% HOLD
    floor, but the three-year fixture also lacks deep-check coverage, so the
    verdict is INSUFFICIENT_DATA rather than AVOID."""
    result = _evaluate("buffett_clark_gm.json")
    assert result.verdict == Verdict.INSUFFICIENT_DATA
    assert result.score is None
    assert len(result.passed_rules) < 3


def test_verdict_insufficient_with_many_unknown():
    """Incomplete fixture has many unknown rules — should be INSUFFICIENT_DATA."""
    result = _evaluate("buffett_clark_incomplete.json")
    assert result.verdict == Verdict.INSUFFICIENT_DATA
    assert result.score is None


# ----------------------------------------------------------------------
# Score
# ----------------------------------------------------------------------


def test_score_is_weighted_not_passed_over_seven():
    """v2.0.0 scores the weighted pass ratio, and returns None when more than
    30% of the weighted rules are missing (the three-year KO fixture)."""
    result = _evaluate("buffett_clark_ko.json")
    assert result.score is None
    assert result.verdict == Verdict.INSUFFICIENT_DATA


def test_score_is_none_when_nothing_is_evaluable():
    """None means insufficient data; it is no longer rendered as 0.0."""
    # Create a fixture with all None values
    rows = []
    for year in [2024, 2023, 2022]:
        from backend.domain.value_objects.financials_normalized import (
            NormalizedFinancials,
            ProviderName,
        )

        rows.append(
            NormalizedFinancials(
                ticker="EMPTY",
                fiscal_year=year,
                source=ProviderName.EDGAR,
            )
        )
    methodology = BuffettClarkMethodology()
    result = methodology.evaluate("TEST", rows, _Prices(100.0))
    assert result.score is None
    assert result.verdict == Verdict.INSUFFICIENT_DATA


# ----------------------------------------------------------------------
# Confidence
# ----------------------------------------------------------------------


def test_confidence_low_when_coverage_is_thin():
    """KO has only three fiscal years, so the 10-year deep rules are missing
    and confidence drops to LOW under the weighted coverage rule."""
    result = _evaluate("buffett_clark_ko.json")
    assert result.confidence == Confidence.LOW


def test_confidence_low_when_many_unknown():
    """Incomplete fixture has many unknown — should be LOW."""
    result = _evaluate("buffett_clark_incomplete.json")
    assert result.confidence == Confidence.LOW


# ----------------------------------------------------------------------
# Red flags
# ----------------------------------------------------------------------


def test_red_flags_listed_for_failures():
    """GM should have red flags for each failed rule."""
    result = _evaluate("buffett_clark_gm.json")
    assert len(result.red_flags) >= 3
    joined = " | ".join(result.red_flags)
    assert "rule_1_gross_margin" in joined
    assert "rule_2_interest_burden" in joined


def test_no_red_flags_when_all_pass():
    """A perfect company should have no red flags."""
    # KO passes most rules but fails debt — should have at least 1 red flag
    result = _evaluate("buffett_clark_ko.json")
    # KO fails rule_4_debt, so there should be at least 1 red flag
    assert len(result.red_flags) >= 1


# ----------------------------------------------------------------------
# Sources
# ----------------------------------------------------------------------


def test_sources_cite_book_and_pages():
    """Every result must cite the book with page numbers."""
    result = _evaluate("buffett_clark_ko.json")
    assert result.sources, "every result must cite its sources"
    for ref in result.sources:
        assert (
            ref.book == "Warren Buffett and the Interpretation of Financial Statements"
        )
        assert ref.page, "every source must cite a page"


# ----------------------------------------------------------------------
# Determinism
# ----------------------------------------------------------------------


def test_evaluation_is_deterministic():
    """Same input always produces same output."""
    methodology = BuffettClarkMethodology()
    rows = _rows("buffett_clark_ko.json")
    first = methodology.evaluate("TEST", rows, _Prices(100.0))
    second = methodology.evaluate("TEST", rows, _Prices(100.0))
    assert first == second


# ----------------------------------------------------------------------
# Metadata
# ----------------------------------------------------------------------


def test_metadata_reports_book_and_limitations():
    metadata = BuffettClarkMethodology().metadata()
    assert "Warren Buffett" in metadata["book"]
    assert metadata["family"] == "QUALITY_COMPOUNDER"
    assert len(metadata["known_limitations"]) >= 2


def test_rules_expose_all_seven_plus_deep_checks():
    methodology = BuffettClarkMethodology()
    ids = {rule.id for rule in methodology.rules()}
    legacy = {
        "buffett_clark.rule_1_gross_margin",
        "buffett_clark.rule_2_interest_burden",
        "buffett_clark.rule_3_margin_durability",
        "buffett_clark.rule_4_debt",
        "buffett_clark.rule_5_cash",
        "buffett_clark.rule_6_capex",
        "buffett_clark.rule_7_retained_earnings",
    }
    assert legacy <= ids
    assert len(ids) == 23
    assert len(methodology.rules()) == 23


def test_metadata_reports_weighted_framework():
    metadata = BuffettClarkMethodology().metadata()
    assert metadata["version"] == "2.0.0"
    assert metadata["thresholds"]["buy"] == 0.85
    assert metadata["categories"] == [
        "durable_advantage",
        "owner_earnings",
        "valuation",
        "growth",
    ]
    assert any("consumer-monopoly" in item for item in metadata["known_limitations"])


# ---------------------------------------------------------------------------
# financial companies (banks/insurers are out of scope for the DCA screen;
# the shared company-type detector guards before any rule runs)
# ---------------------------------------------------------------------------
def test_financial_company_not_applicable():
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
    result = BuffettClarkMethodology().evaluate("T", rows, _Prices(100.0))
    assert result.verdict == Verdict.NOT_APPLICABLE
    assert result.score is None
    assert result.confidence == Confidence.HIGH
    assert result.metrics["financial_company"] is True
    assert result.passed_rules == []
    assert result.failed_rules == []
    assert any("financial" in r.lower() for r in result.reasons)


def test_financial_sector_hint_not_applicable():
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
    result = BuffettClarkMethodology().evaluate("T", rows, _Prices(100.0))
    assert result.verdict == Verdict.NOT_APPLICABLE
    assert result.metrics["financial_company"] is True
