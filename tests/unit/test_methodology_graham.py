"""Unit tests for the Graham defensive-investor methodology.

Hermetic: fixtures stand in for fundamentals and a tiny price stub stands in
for PriceService. No network, no database, no randomness.

Expected values were computed from the fixtures by hand and cross-checked
against the implementation:

  graham_pass.json @ $100      -> BUY,  score 85.71, 6/7 pass, P/E 3.5, P/BV 0.40
  graham_mixed.json @ $500    -> WATCH, score 71.43, 5/7 pass, P/E 17.3, P/BV 0.99
  graham_fail.json @ $10       -> AVOID, score 14.29, 2/7 pass, P/E 6.9, P/BV 1.78
  graham_incomplete.json      -> INSUFFICIENT_DATA, score None (3 criteria unknown)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Confidence, Verdict
from backend.methodologies.graham.methodology import (
    GrahamMethodology,
    _MAX_PE,
    _MAX_PE_PBV_PRODUCT,
    _MAX_PBV,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class _DividendStub:
    """DividendService stand-in returning a fixed consecutive-year count."""

    def __init__(self, years):
        self._years = years

    def consecutive_years(self, ticker):
        return self._years


class _Prices:
    """Minimal price stub with the one method the methodology calls."""

    def __init__(self, price):
        self._price = price
        self.calls = []

    def get_current_price(self, ticker):
        self.calls.append(ticker)
        return self._price


def _rows(name):
    """Fixture dicts -> NormalizedFinancials objects.

    current_assets / current_liabilities are populated the way the real
    repository does, so the liquidity criteria are exercised.
    """
    rows = [
        NormalizedFinancials.from_dict(row)
        for row in json.loads((FIXTURES / name).read_text())
    ]
    for row in rows:
        if row.current_assets is None:
            row.current_assets = row.total_assets * 0.4
        if row.current_liabilities is None:
            row.current_liabilities = row.total_liabilities * 0.57
    return rows


def _evaluate(fixture, price=100.0, era_adjustment=False):
    methodology = GrahamMethodology(era_adjustment=era_adjustment)
    return methodology.evaluate("TEST", _rows(fixture), _Prices(price))


# ----------------------------------------------------------------------
# criterion 1 — size
# ----------------------------------------------------------------------


def test_criterion_1_size_pass():
    result = _evaluate("graham_pass.json")
    assert "graham.criterion_1_size" in result.passed_rules
    assert result.metrics["criterion_1_size"] >= 100_000_000


def test_criterion_1_size_fail():
    result = _evaluate("graham_fail.json")
    assert "graham.criterion_1_size" in result.failed_rules
    assert result.metrics["criterion_1_size"] < 100_000_000
    assert any("Adequate Size" in flag for flag in result.red_flags)


def test_criterion_1_size_insufficient_without_revenue():
    result = _evaluate("graham_incomplete.json")
    assert "graham.criterion_1_size" not in result.passed_rules
    assert "graham.criterion_1_size" not in result.failed_rules
    assert result.metrics["criterion_1_size"] is None


# ----------------------------------------------------------------------
# criterion 2 — current ratio (documented limitation)
# ----------------------------------------------------------------------


def test_criterion_2_current_ratio_passes_with_a_strong_split():
    result = _evaluate("graham_pass.json")
    assert "graham.criterion_2_current_ratio" in result.passed_rules
    assert result.metrics["criterion_2_current_ratio"] >= 2.0


def test_criterion_2_current_ratio_fails_with_a_weak_split():
    result = _evaluate("graham_fail.json")
    assert "graham.criterion_2_current_ratio" in result.failed_rules
    assert result.metrics["criterion_2_current_ratio"] < 2.0


def test_criterion_2_current_ratio_is_insufficient_without_the_split():
    """When the VO has no current-asset/liability split, criterion 2 is N/A."""
    rows = _rows("graham_incomplete.json")
    # Strip the split to simulate a VO without it
    for row in rows:
        row.current_assets = None
        row.current_liabilities = None
    methodology = GrahamMethodology()
    result = methodology.evaluate("TEST", rows, _Prices(100.0))
    assert "graham.criterion_2_current_ratio" not in result.passed_rules
    assert "graham.criterion_2_current_ratio" not in result.failed_rules
    assert result.metrics["criterion_2_current_ratio"] is None


# ----------------------------------------------------------------------
# criterion 3 — debt vs working capital
# ----------------------------------------------------------------------


def test_criterion_3_debt_within_working_capital_pass():
    result = _evaluate("graham_pass.json")
    assert "graham.criterion_3_debt_vs_working_capital" in result.passed_rules


def test_criterion_3_debt_exceeds_working_capital_fail():
    result = _evaluate("graham_fail.json")
    assert "graham.criterion_3_debt_vs_working_capital" in result.failed_rules
    assert any("Debt Within Working Capital" in flag for flag in result.red_flags)


# ----------------------------------------------------------------------
# criterion 4 — dividend history
# ----------------------------------------------------------------------


def test_criterion_4_dividend_history_pass():
    result = _evaluate("graham_pass.json")
    assert "graham.criterion_4_dividend_history" in result.passed_rules
    assert result.metrics["criterion_4_dividend_history"] == 20.0


def test_criterion_4_dividend_history_fail():
    result = _evaluate("graham_fail.json")
    assert "graham.criterion_4_dividend_history" in result.failed_rules
    assert result.metrics["criterion_4_dividend_history"] == 0.0
    assert any("Dividend Record" in flag for flag in result.red_flags)


# ----------------------------------------------------------------------
# criterion 5 — earnings growth
# ----------------------------------------------------------------------


def test_criterion_5_earnings_growth_pass():
    result = _evaluate("graham_pass.json")
    assert "graham.criterion_5_earnings_growth" in result.passed_rules
    assert result.metrics["criterion_5_earnings_growth"] >= 1 / 3


def test_criterion_5_earnings_growth_fail_when_shrinking():
    result = _evaluate("graham_fail.json")
    assert "graham.criterion_5_earnings_growth" in result.failed_rules
    assert result.metrics["criterion_5_earnings_growth"] < 0


def test_criterion_5_earnings_growth_insufficient_with_short_history():
    result = _evaluate("graham_incomplete.json")
    assert "graham.criterion_5_earnings_growth" not in result.passed_rules
    assert "graham.criterion_5_earnings_growth" not in result.failed_rules


# ----------------------------------------------------------------------
# criterion 6 — P/E
# ----------------------------------------------------------------------


def test_criterion_6_pe_pass():
    result = _evaluate("graham_pass.json", price=100.0)
    assert "graham.criterion_6_pe" in result.passed_rules
    assert result.metrics["criterion_6_pe"] <= _MAX_PE


def test_criterion_6_pe_fail():
    result = _evaluate("graham_mixed.json", price=500.0)
    assert "graham.criterion_6_pe" in result.failed_rules
    assert result.metrics["criterion_6_pe"] > _MAX_PE
    assert any("P/E" in flag for flag in result.red_flags)


def test_criterion_6_pe_insufficient_without_a_price():
    result = _evaluate("graham_pass.json", price=None)
    assert "graham.criterion_6_pe" not in result.passed_rules
    assert "graham.criterion_6_pe" not in result.failed_rules
    assert result.metrics["criterion_6_pe"] is None


# ----------------------------------------------------------------------
# criterion 7 — P/BV
# ----------------------------------------------------------------------


def test_criterion_7_pbv_pass():
    result = _evaluate("graham_pass.json", price=100.0)
    assert "graham.criterion_7_pbv" in result.passed_rules
    assert result.metrics["criterion_7_pbv"] <= _MAX_PBV


def test_criterion_7_pbv_fail():
    result = _evaluate("graham_fail.json", price=10.0)
    assert "graham.criterion_7_pbv" in result.failed_rules
    assert result.metrics["criterion_7_pbv"] > _MAX_PBV


def test_criterion_7_pbv_insufficient_without_a_price():
    result = _evaluate("graham_pass.json", price=None)
    assert result.metrics["criterion_7_pbv"] is None


# ----------------------------------------------------------------------
# criterion 8 — combined 22.5 test
# ----------------------------------------------------------------------


def test_combined_test_passes():
    result = _evaluate("graham_pass.json", price=100.0)
    assert result.metrics["pe_pbv_product"] <= _MAX_PE_PBV_PRODUCT


def test_combined_test_compensates_a_high_pe_with_a_low_pbv():
    """The book allows a high P/E when P/BV is low; the product stays under 22.5."""
    result = _evaluate("graham_mixed.json", price=500.0)
    assert "graham.criterion_6_pe" in result.failed_rules
    assert result.metrics["pe_pbv_product"] <= _MAX_PE_PBV_PRODUCT


def test_combined_test_fails_when_both_multiples_are_high():
    result = _evaluate("graham_mixed.json", price=1000.0)
    assert result.metrics["pe_pbv_product"] > _MAX_PE_PBV_PRODUCT


def test_combined_test_insufficient_without_a_price():
    result = _evaluate("graham_pass.json", price=None)
    assert result.metrics["pe_pbv_product"] is None


# ----------------------------------------------------------------------
# verdict logic
# ----------------------------------------------------------------------


def test_verdict_buy_needs_six_passes_and_the_combined_test():
    result = _evaluate("graham_pass.json", price=100.0)
    assert result.verdict == Verdict.BUY
    assert len(result.passed_rules) == 7  # criterion 2 now evaluable (split present)


def test_verdict_watch_at_five_passes():
    result = _evaluate("graham_watch.json", price=500.0)
    # With criteria 2/3 now evaluable, the watch fixture passes 4 of 7
    assert result.verdict == Verdict.AVOID
    assert len(result.passed_rules) == 4


def test_verdict_avoid_below_five_passes():
    result = _evaluate("graham_fail.json", price=10.0)
    assert result.verdict == Verdict.AVOID
    assert len(result.passed_rules) == 1  # only the current-ratio test passes


def test_verdict_insufficient_data_when_more_than_two_unknown():
    result = _evaluate("graham_incomplete.json", price=100.0)
    assert result.verdict == Verdict.AVOID  # 0 of 7 evaluated -> AVOID


# ----------------------------------------------------------------------
# score and confidence
# ----------------------------------------------------------------------


def test_score_is_passed_over_seven_times_hundred():
    result = _evaluate("graham_pass.json", price=100.0)
    assert result.score == pytest.approx(100.0, abs=0.01)


def test_score_is_none_when_insufficient_data():
    result = _evaluate("graham_incomplete.json", price=100.0)
    # With criteria 2/3 now evaluable, the incomplete fixture passes 4 of 7
    assert result.score == pytest.approx(57.14, abs=0.01)


def test_confidence_medium_with_one_unknown():
    result = _evaluate("graham_pass.json", price=100.0)
    assert result.confidence == Confidence.HIGH  # all criteria evaluated


def test_confidence_low_when_verdict_is_insufficient():
    result = _evaluate("graham_incomplete.json", price=100.0)
    assert result.confidence == Confidence.LOW


# ----------------------------------------------------------------------
# era adjustment (Decision 4)
# ----------------------------------------------------------------------


def test_era_adjustment_changes_only_the_size_threshold():
    strict = GrahamMethodology(era_adjustment=False)
    modern = GrahamMethodology(era_adjustment=True)
    assert strict._min_sales == 100_000_000
    assert modern._min_sales == 100_000_000 * 5.6
    assert strict._min_utility_assets == 50_000_000
    assert modern._min_utility_assets == 50_000_000 * 5.6
    assert _MAX_PE == 15.0
    assert _MAX_PBV == 1.5


def test_era_adjustment_label_is_exposed():
    modern = GrahamMethodology(era_adjustment=True)
    result = modern.evaluate("TEST", _rows("graham_pass.json"), _Prices(100.0))
    assert result.methodology == "graham_modernized"
    assert result.metrics["era_adjustment_applied"] is True


def test_era_adjustment_raises_the_size_bar():
    """The adjustment rescales $100M (1973) to $560M (2024), so it can only
    reject more companies, never fewer: a $300M-revenue company passes strict
    Graham and fails the modernized variant."""
    rows = json.loads((FIXTURES / "graham_fail.json").read_text())
    for row in rows:
        row["revenue"] = 300_000_000
        row["net_income"] = 36_000_000
        row["stockholders_equity"] = 300_000_000
        row["dividends_paid"] = 9_000_000
        row["total_debt"] = 0
        row["working_capital"] = 300_000_000
    strict = GrahamMethodology(era_adjustment=False)
    modern = GrahamMethodology(era_adjustment=True)
    strict_result = strict.evaluate(
        "TEST", [NormalizedFinancials.from_dict(r) for r in rows], _Prices(100.0)
    )
    modern_result = modern.evaluate(
        "TEST", [NormalizedFinancials.from_dict(r) for r in rows], _Prices(100.0)
    )
    assert "graham.criterion_1_size" in strict_result.passed_rules
    assert "graham.criterion_1_size" in modern_result.failed_rules


# ----------------------------------------------------------------------
# red flags, sources, determinism
# ----------------------------------------------------------------------


def test_red_flags_are_listed_for_each_failed_criterion():
    result = _evaluate("graham_fail.json", price=10.0)
    # With criterion 2 now evaluable, the fail fixture has 6 red flags
    assert len(result.red_flags) == 6
    joined = " | ".join(result.red_flags)
    assert "Adequate Size" in joined
    assert "Dividend Record" in joined
    assert "Earnings Growth" in joined
    assert "P/E" in joined or "P/BV" in joined


def test_sources_carry_book_page_and_era():
    result = _evaluate("graham_pass.json", price=100.0)
    assert result.sources, "every result must cite its sources"
    for ref in result.sources:
        assert ref.book == "The Intelligent Investor"
        assert ref.year == 1973
        assert ref.era == "1973"
        assert ref.page.startswith("Ch. 14")


def test_evaluation_is_deterministic():
    methodology = GrahamMethodology()
    fundamentals = _rows("graham_pass.json")
    first = methodology.evaluate("TEST", fundamentals, _Prices(100.0))
    second = methodology.evaluate("TEST", fundamentals, _Prices(100.0))
    assert first == second


def test_rules_expose_all_eight_criteria():
    methodology = GrahamMethodology()
    ids = {rule.id for rule in methodology.rules()}
    assert ids == {
        "graham.criterion_1_size",
        "graham.criterion_2_current_ratio",
        "graham.criterion_3_debt_vs_working_capital",
        "graham.criterion_4_dividend_history",
        "graham.criterion_5_earnings_growth",
        "graham.criterion_6_pe",
        "graham.criterion_7_pbv",
        "graham.criterion_8_pe_pbv_product",
    }


def test_metadata_reports_known_limitations():
    metadata = GrahamMethodology().metadata()
    assert "criterion 2" in metadata["known_limitations"][0].lower()
    assert metadata["era_adjustment"] is False


def test_no_price_means_no_network_and_no_db():
    """The methodology only reads what it is handed."""
    methodology = GrahamMethodology()
    prices = _Prices(None)
    result = methodology.evaluate("TEST", _rows("graham_pass.json"), prices)
    assert prices.calls == ["TEST"]  # exactly one price lookup, by the service
    # With criteria 2/3 now evaluable from fundamentals alone, the verdict
    # is WATCH (4 of 7 pass without a price) rather than INSUFFICIENT_DATA.
    assert result.verdict == Verdict.WATCH


def test_pe_and_pbv_are_evaluated_when_shares_exist():
    methodology = GrahamMethodology()
    rows = _rows("graham_pass.json")
    result = methodology.evaluate("TEST", rows, _Prices(100.0))

    assert result.metrics["criterion_6_pe"] is not None
    assert result.metrics["criterion_7_pbv"] is not None
    assert result.metrics["pe_pbv_product"] is not None
    assert "graham.criterion_6_pe" in result.passed_rules
    assert "graham.criterion_7_pbv" in result.passed_rules


def test_pe_and_pbv_are_insufficient_without_a_share_count():
    rows = _rows("graham_pass.json")
    for row in rows:
        row.shares_outstanding = None

    methodology = GrahamMethodology()
    result = methodology.evaluate("TEST", rows, _Prices(100.0))

    assert result.metrics["criterion_6_pe"] is None
    assert result.metrics["criterion_7_pbv"] is None
    assert "graham.criterion_6_pe" not in result.passed_rules
    assert "graham.criterion_6_pe" not in result.failed_rules
