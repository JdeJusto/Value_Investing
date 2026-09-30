"""Unit tests for the UI adapter (backend/services/ui_adapter.py).

The Streamlit page itself is a thin view; these tests cover the pure
transformation helpers: formatting, the methodologies view (table, details,
disagreement summary) and the DCF view (labels, sensitivity rows).
No network, no database, no prices persisted.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.methodologies.base import Confidence, Verdict
from backend.services.ui_adapter import (
    DASH,
    build_dcf_view,
    build_methodologies_view,
    disagreement_narrative,
    fmt_money_short,
    fmt_or_dash,
    run_dcf,
    run_methodologies,
)
from backend.valuation.base import DCFResult


@dataclass
class _FakeResult:
    methodology: str
    family: str
    verdict: Verdict
    score: float | None
    confidence: Confidence
    reasons: list
    metrics: dict
    red_flags: list


def _fake(
    methodology,
    family,
    verdict,
    score,
    confidence=Confidence.HIGH,
    reasons=None,
    metrics=None,
    red_flags=None,
):
    return _FakeResult(
        methodology=methodology,
        family=family,
        verdict=verdict,
        score=score,
        confidence=confidence,
        reasons=reasons or [f"{methodology} reason"],
        metrics=metrics or {},
        red_flags=red_flags or [],
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def test_fmt_or_dash_none_and_numbers():
    assert fmt_or_dash(None) == DASH
    assert fmt_or_dash(20.0) == "20.00"
    assert fmt_or_dash(0.1833, percent=True) == "18.33%"
    assert fmt_or_dash(None, percent=True) == DASH


def test_fmt_money_short_scales():
    assert fmt_money_short(None) == DASH
    assert fmt_money_short(1.4e12) == "$1.40T"
    assert fmt_money_short(23.5e9) == "$23.5B"
    assert fmt_money_short(980e6) == "$980.0M"
    assert fmt_money_short(1234.0) == "$1,234"


# ---------------------------------------------------------------------------
# Methodologies view
# ---------------------------------------------------------------------------
def test_build_methodologies_view_table_and_category():
    results = [
        _fake("graham", "DEEP_VALUE", Verdict.AVOID, 28.57),
        _fake(
            "lynch_garp",
            "GARP",
            Verdict.BUY,
            None,
            reasons=["[PASS] dividend paid in 10 of 10 years"],
            metrics={"lynch_category_label": "Slow Grower (mature, dividend-focused)"},
        ),
    ]
    view = build_methodologies_view("KO", results)
    assert view.ticker == "KO"
    assert len(view.table) == 2
    assert view.table[0]["Methodology"] == "graham"
    assert view.table[0]["Verdict"] == "AVOID"
    assert view.table[0]["Score"] == "28.57"
    assert view.table[1]["Score"] == "—"
    assert view.details[1]["category"] == "Slow Grower (mature, dividend-focused)"
    assert view.category == "Slow Grower (mature, dividend-focused)"


def test_disagreement_summary_groups_families():
    results = [
        _fake("graham", "DEEP_VALUE", Verdict.AVOID, 20.0),
        _fake("graham_dodd", "DEEP_VALUE", Verdict.AVOID, 25.0),
        _fake("buffett_clark", "QUALITY_COMPOUNDER", Verdict.BUY, 71.4),
        _fake("fisher_quantitative_subset", "QUALITY_COMPOUNDER", Verdict.BUY, 100.0),
    ]
    view = build_methodologies_view("AAPL", results)
    assert view.agreement is False
    assert len(view.family_lines) == 2
    assert "DEEP_VALUE → graham=AVOID, graham_dodd=AVOID" in view.family_lines
    assert view.explanation is not None
    assert "value screen(s)" in view.explanation
    assert "quality screen(s)" in view.explanation
    assert len(view.reason_lines) == 4


def test_agreement_when_all_verdicts_match():
    results = [
        _fake("graham", "DEEP_VALUE", Verdict.BUY, 80.0),
        _fake("graham_dodd", "DEEP_VALUE", Verdict.BUY, 75.0),
    ]
    view = build_methodologies_view("X", results)
    assert view.agreement is True
    assert view.family_lines == []
    assert view.explanation is None


def test_narrative_value_vs_quality_when_pattern_matches():
    # AAPL-like: a deep-value screen rejects what a quality screen rewards.
    results = [
        _fake("graham", "DEEP_VALUE", Verdict.AVOID, 20.0),
        _fake("buffett_clark", "QUALITY_COMPOUNDER", Verdict.BUY, 71.4),
    ]
    narrative = disagreement_narrative(results)
    assert "value screen(s)" in narrative["explanation"]
    assert "quality screen(s)" in narrative["explanation"]
    assert "1 of 2" in narrative["consensus"]


def test_narrative_neutral_for_mixed_cyclical_pattern():
    # XOM-like: no BUY anywhere; the long value/quality paragraph would be
    # misleading, so the neutral line is used instead.
    results = [
        _fake("graham", "DEEP_VALUE", Verdict.AVOID, 14.3),
        _fake("graham_dodd", "DEEP_VALUE", Verdict.HOLD, 50.0),
        _fake("buffett_clark", "QUALITY_COMPOUNDER", Verdict.AVOID, 28.6),
        _fake("fisher_quantitative_subset", "QUALITY_COMPOUNDER", Verdict.AVOID, 0.0),
        _fake("lynch_garp", "GARP", Verdict.AVOID, 20.0),
    ]
    narrative = disagreement_narrative(results)
    assert "answer different questions" in narrative["explanation"]
    assert "value screen(s)" not in narrative["explanation"]
    assert "No methodology gives BUY" in narrative["consensus"]


def test_narrative_never_declares_a_winner():
    for results in (
        [
            _fake("graham", "DEEP_VALUE", Verdict.AVOID, 20.0),
            _fake("buffett_clark", "QUALITY_COMPOUNDER", Verdict.BUY, 71.4),
        ],
        [
            _fake("graham", "DEEP_VALUE", Verdict.BUY, 80.0),
            _fake("buffett_clark", "QUALITY_COMPOUNDER", Verdict.BUY, 71.4),
        ],
    ):
        narrative = disagreement_narrative(results)
        text = (narrative["explanation"] + " " + narrative["consensus"]).lower()
        assert "recommended" not in text
        assert (
            "winner is declared" in text
            or "no single winner" in text
            or "all methodologies give buy" in text
        )


# ---------------------------------------------------------------------------
# DCF view
# ---------------------------------------------------------------------------
def _dcf_result(**overrides):
    base = {
        "ticker": "T",
        "intrinsic_value_per_share": 100.0,
        "current_price": 80.0,
        "margin_of_safety": 0.2,
        "verdict": "UNDERVALUED",
        "wacc": 0.09,
        "fcf_base": 5.0,
        "fcf_years": 3,
        "growth_1_5": 0.10,
        "growth_6_10": 0.05,
        "terminal_growth": 0.025,
        "shares_outstanding": 1_000_000_000.0,
    }
    base.update(overrides)
    return DCFResult(**base)


def test_build_dcf_view_standard_and_sensitivity_rows():
    sensitivity = {
        (0.07, 0.08): 80.0,
        (0.07, 0.10): 85.0,
        (0.07, 0.12): 90.0,
        (0.09, 0.08): 95.0,
        (0.09, 0.10): 100.0,
        (0.09, 0.12): 105.0,
        (0.11, 0.08): 110.0,
        (0.11, 0.10): 115.0,
        (0.11, 0.12): 120.0,
    }
    result = _dcf_result(sensitivity=sensitivity)
    view = build_dcf_view(result)
    assert view.variant == "standard"
    assert view.variant_label == "standard DCF (free cash flow)"
    assert view.discount_label == "WACC"
    assert view.base_text == "FCF base (3y avg)"
    assert view.is_insufficient is False
    assert len(view.sensitivity_rows) == 3
    assert list(view.sensitivity_rows[0]) == ["WACC \\ Growth", "g-2%", "g", "g+2%"]
    assert view.sensitivity_rows[1]["g"] == 100.0


def test_build_dcf_view_ddm_labels():
    result = _dcf_result(variant="ddm_financial_two_stage")
    view = build_dcf_view(result)
    assert view.variant_label == "financial — two-stage dividend discount model"
    assert view.discount_label == "Cost of equity"
    assert view.base_text == "Dividend per share"
    assert view.sensitivity_rows == []


def test_build_dcf_view_insufficient():
    result = DCFResult(
        ticker="BAC",
        intrinsic_value_per_share=None,
        current_price=None,
        margin_of_safety=None,
        verdict="INSUFFICIENT_DATA",
        wacc=None,
        fcf_base=None,
        fcf_years=None,
        growth_1_5=None,
        growth_6_10=None,
        terminal_growth=0.025,
        shares_outstanding=None,
        reasons=["Financial company (banks/insurers): ..."],
        missing_inputs=["dividends per share"],
        variant="ddm_financial",
    )
    view = build_dcf_view(result)
    assert view.is_insufficient is True
    assert view.missing_inputs == ["dividends per share"]
    assert view.sensitivity_rows == []


# ---------------------------------------------------------------------------
# Orchestration (hermetic: no rows, no price service reads)
# ---------------------------------------------------------------------------
def test_run_methodologies_returns_one_row_per_methodology():
    view = run_methodologies("TEST", [], None)
    assert len(view.table) >= 6
    names = {row["Methodology"] for row in view.table}
    assert {"graham", "buffett_clark", "fisher_quantitative_subset"} <= names


def test_run_dcf_with_no_rows_is_insufficient():
    view = run_dcf("TEST", [], None)
    assert view.is_insufficient is True
    assert view.ticker == "TEST"
