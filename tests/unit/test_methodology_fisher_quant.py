"""Unit tests for the ``fisher_quantitative_subset`` methodology.

Hermetic: fixtures and inline rows stand in for fundamentals. No network,
no database, no price lookups, no randomness.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Confidence, Verdict
from backend.methodologies.fisher_quantitative_subset.methodology import (
    FisherQuantitativeSubsetMethodology,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MODULE_DIR = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "methodologies"
    / "fisher_quantitative_subset"
)

R1 = "fisher_quantitative_subset.rule_1_rnd_intensity"
R2 = "fisher_quantitative_subset.rule_2_profit_margin_quality"
R3 = "fisher_quantitative_subset.rule_3_cost_control_stability"
R4 = "fisher_quantitative_subset.rule_4_share_dilution"


class _Prices:
    """Stub that fails loudly if a methodology reaches for prices."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        raise AssertionError(f"methodology reached for {name}")


def _row(
    year,
    revenue,
    gross_profit=None,
    net_income=None,
    operating_income=None,
    research_development=None,
    shares_outstanding=None,
    split_adjustment_factor=None,
    sector=None,
):
    data = {
        "ticker": "TEST",
        "fiscal_year": year,
        "revenue": revenue,
        "period": "FY",
        "currency": "USD",
        "source": "sec_edgar",
    }
    if gross_profit is not None:
        data["gross_profit"] = gross_profit
    if net_income is not None:
        data["net_income"] = net_income
    if operating_income is not None:
        data["operating_income"] = operating_income
    if research_development is not None:
        data["research_development"] = research_development
    if shares_outstanding is not None:
        data["shares_outstanding"] = shares_outstanding
    if split_adjustment_factor is not None:
        data["split_adjustment_factor"] = split_adjustment_factor
    if sector is not None:
        data["sector"] = sector
    return NormalizedFinancials.from_dict(data)


def _gross_margin_rows(margins, revenue=100_000_000_000):
    """Newest-first rows whose gross margin is exactly *margins[0..] * revenue*."""
    rows = []
    for i, margin in enumerate(margins):
        rows.append(_row(2024 - i, revenue, gross_profit=round(margin * revenue)))
    return rows


def _healthy_rows(
    past_shares,
    current_shares,
    net_ratio=0.20,
    op_ratio=0.25,
    rnd_ratio=0.09,
    past_split_factor=None,
):
    """Eleven years of otherwise-healthy rows; shares fixed at 10y-ago/now."""
    rows = []
    revenue = 100_000_000_000
    for year in range(2014, 2025):
        shares = past_shares if year == 2014 else current_shares
        rows.append(
            _row(
                year,
                revenue,
                gross_profit=40_000_000_000,
                net_income=net_ratio * revenue,
                operating_income=op_ratio * revenue,
                research_development=rnd_ratio * revenue,
                shares_outstanding=shares,
                split_adjustment_factor=(past_split_factor if year == 2014 else None),
            )
        )
    return rows


def _full_margin_rows(margins, rnd_ratio=0.06, net_ratio=0.20, op_ratio=0.25):
    """Five years with margins, margins-left margins and all income fields."""
    rows = []
    revenue = 100_000_000_000
    for i, margin in enumerate(margins):
        rows.append(
            _row(
                2024 - i,
                revenue,
                gross_profit=round(margin * revenue),
                net_income=net_ratio * revenue,
                operating_income=op_ratio * revenue,
                research_development=rnd_ratio * revenue,
                shares_outstanding=15_000_000_000,
            )
        )
    return rows


def _ko_shape_rows():
    """KO-like profile: R&D is not reported, everything else passes."""
    rows = []
    revenue = 100_000_000_000
    for year in range(2014, 2025):
        rows.append(
            _row(
                year,
                revenue,
                gross_profit=42_000_000_000,
                net_income=0.27 * revenue,
                operating_income=0.29 * revenue,
                shares_outstanding=4_300_000_000,
            )
        )
    return rows


def _fixture_rows(name):
    raw = json.loads((FIXTURES / name).read_text())
    return [NormalizedFinancials.from_dict(r) for r in raw]


def _evaluate(rows, prices=None):
    methodology = FisherQuantitativeSubsetMethodology()
    if prices is None:
        prices = _Prices()
    return methodology.evaluate("TEST", rows, prices)


def _status(result, rule_id):
    marker = rule_id + ":"
    for reason in result.reasons:
        status, _, rest = reason.partition(" ")
        if rest.startswith(marker):
            return status
    raise AssertionError(f"rule not found in reasons: {rule_id}")


# ---------------------------------------------------------------------------
# Rule 1 — R&D intensity (point 3)
# ---------------------------------------------------------------------------
def test_rule_1_rnd_pass():
    res = _evaluate([_row(2024, 100_000_000_000, research_development=8_500_000_000)])
    assert _status(res, R1) == "PASS"


def test_rule_1_rnd_pass_boundary_8pct():
    res = _evaluate([_row(2024, 100_000_000_000, research_development=8_000_000_000)])
    assert _status(res, R1) == "PASS"


def test_rule_1_rnd_watch():
    # 6% was a PASS at the old 5% bar; the 2026-09 calibration moved the PASS
    # line to 8%, so a mid-range compounder now reads WATCH.
    res = _evaluate([_row(2024, 100_000_000_000, research_development=6_000_000_000)])
    assert _status(res, R1) == "WATCH"


def test_rule_1_rnd_fail():
    res = _evaluate([_row(2024, 100_000_000_000, research_development=1_000_000_000)])
    assert _status(res, R1) == "FAIL"


def test_rule_1_rnd_insufficient():
    res = _evaluate([_row(2024, 100_000_000_000)])
    assert _status(res, R1) == "INSUFFICIENT_DATA"


def test_rule_1_tech_5pct_watch():
    # 5% sits in the innovation-led WATCH band (4-8%): a software company
    # spent materially, but the sector bar still demands ~8% for a PASS.
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                research_development=5_000_000_000,
                sector="Technology",
            )
        ]
    )
    assert _status(res, R1) == "WATCH"


def test_rule_1_tech_9pct_pass():
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                research_development=9_000_000_000,
                sector="Information Technology",
            )
        ]
    )
    assert _status(res, R1) == "PASS"


def test_rule_1_tech_3pct_fail():
    # Healthcare is in the strict tier too: 3% is below its 4% floor.
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                research_development=3_000_000_000,
                sector="Healthcare",
            )
        ]
    )
    assert _status(res, R1) == "FAIL"


def test_rule_1_staples_1pct_watch():
    # 1% is inside the low-tier WATCH band (0.5-2%): staples do not need a
    # large R&D line, but a token spend still reads WATCH, not AVOID.
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                research_development=1_000_000_000,
                sector="Consumer Defensive",
            )
        ]
    )
    assert _status(res, R1) == "WATCH"


def test_rule_1_staples_2pct_pass():
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                research_development=2_000_000_000,
                sector="Consumer Defensive",
            )
        ]
    )
    assert _status(res, R1) == "PASS"


def test_rule_1_utilities_0_3pct_fail():
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                research_development=300_000_000,
                sector="Utilities",
            )
        ]
    )
    assert _status(res, R1) == "FAIL"


def test_rule_1_energy_0_8pct_watch():
    res = _evaluate(
        [_row(2024, 100_000_000_000, research_development=800_000_000, sector="Energy")]
    )
    assert _status(res, R1) == "WATCH"


def test_rule_1_industrials_3pct_watch():
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                research_development=3_000_000_000,
                sector="Industrials",
            )
        ]
    )
    assert _status(res, R1) == "WATCH"


def test_rule_1_unknown_sector_keeps_8pct_bar():
    # No sector metadata: the historical 8%/2% large-cap bar still applies.
    high = _evaluate([_row(2024, 100_000_000_000, research_development=8_500_000_000)])
    mid = _evaluate([_row(2024, 100_000_000_000, research_development=5_000_000_000)])
    low = _evaluate([_row(2024, 100_000_000_000, research_development=1_000_000_000)])
    assert _status(high, R1) == "PASS"
    assert _status(mid, R1) == "WATCH"
    assert _status(low, R1) == "FAIL"


def test_rule_1_metrics_report_applied_tier():
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                research_development=9_000_000_000,
                sector="Technology",
            )
        ]
    )
    assert res.metrics["rnd_thresholds"] == {"pass": 0.08, "watch": 0.04}


# ---------------------------------------------------------------------------
# Rule 2 — worthwhile profit margin (point 5)
# ---------------------------------------------------------------------------
def test_rule_2_margins_pass():
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                net_income=25_000_000_000,
                operating_income=30_000_000_000,
            )
        ]
    )
    assert _status(res, R2) == "PASS"


def test_rule_2_watch_net_above_op_below():
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                net_income=12_000_000_000,
                operating_income=8_000_000_000,
            )
        ]
    )
    assert _status(res, R2) == "WATCH"


def test_rule_2_watch_op_above_net_below():
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                net_income=8_000_000_000,
                operating_income=20_000_000_000,
            )
        ]
    )
    assert _status(res, R2) == "WATCH"


def test_rule_2_fail_net_below_5pct():
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                net_income=4_000_000_000,
                operating_income=20_000_000_000,
            )
        ]
    )
    assert _status(res, R2) == "FAIL"


def test_rule_2_fail_both_below():
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                net_income=8_000_000_000,
                operating_income=10_000_000_000,
            )
        ]
    )
    assert _status(res, R2) == "FAIL"


def test_rule_2_insufficient_missing_op():
    res = _evaluate([_row(2024, 100_000_000_000, net_income=12_000_000_000)])
    assert _status(res, R2) == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Rule 3 — cost-control stability (point 10)
# ---------------------------------------------------------------------------
def test_rule_3_stability_pass():
    res = _evaluate(_gross_margin_rows([0.42, 0.42, 0.425, 0.42, 0.42]))
    assert _status(res, R3) == "PASS"


def test_rule_3_stability_watch():
    res = _evaluate(_gross_margin_rows([0.55, 0.48, 0.57, 0.45, 0.50]))
    assert _status(res, R3) == "WATCH"


def test_rule_3_stability_fail():
    res = _evaluate(_gross_margin_rows([0.70, 0.45, 0.60, 0.35, 0.55]))
    assert _status(res, R3) == "FAIL"


def test_rule_3_insufficient_short_history():
    res = _evaluate(_gross_margin_rows([0.42, 0.42, 0.42]))
    assert _status(res, R3) == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Rule 4 — dilution risk (point 13)
# ---------------------------------------------------------------------------
def test_rule_4_no_dilution_pass():
    res = _evaluate(_healthy_rows(18_000_000_000, 15_000_000_000))
    assert _status(res, R4) == "PASS"


def test_rule_4_small_increase_watch():
    res = _evaluate(_healthy_rows(10_000_000_000, 10_500_000_000))
    assert _status(res, R4) == "WATCH"


def test_rule_4_large_increase_fail():
    res = _evaluate(_healthy_rows(10_000_000_000, 11_500_000_000))
    assert _status(res, R4) == "FAIL"


def test_rule_4_insufficient_no_10y():
    rows = _full_margin_rows([0.42, 0.42, 0.42, 0.42, 0.42])
    assert _status(_evaluate(rows), R4) == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Rule 4 — split adjustment (point 13, hermetic via row-carried factors)
# ---------------------------------------------------------------------------
def test_rule_4_split_adjustment_turns_apparent_dilution_into_pass():
    """AAPL 2015-2025 profile: as-reported shares +159% (4:1 split of 2020),
    but on split-adjusted basis (factor 4.0 on the 10y-ago row) they fell —
    massive buybacks. Must read PASS, not FAIL."""
    rows = _healthy_rows(5_750_000_000, 14_900_000_000, past_split_factor=4.0)
    res = _evaluate(rows)
    assert _status(res, R4) == "PASS"
    assert "split-adjusted" in next(
        r for r in res.reasons if r.partition(" ")[2].startswith(R4 + ":")
    )


def test_rule_4_split_adjustment_watch_from_fail():
    """A mild split (1.25x) turns an apparent +30% 'dilution' into +4% WATCH."""
    rows = _healthy_rows(10_000_000_000, 13_000_000_000, past_split_factor=1.25)
    assert _status(_evaluate(rows), R4) == "WATCH"


def test_rule_4_split_factor_default_keeps_past_behavior():
    """Rows without a factor (1.0) behave exactly as before the fix."""
    res = _evaluate(_healthy_rows(10_000_000_000, 11_500_000_000))
    assert _status(res, R4) == "FAIL"
    res = _evaluate(_healthy_rows(18_000_000_000, 15_000_000_000))
    assert _status(res, R4) == "PASS"


def test_rule_4_split_factor_zero_or_negative_treated_as_one():
    """Garbage factor data must never corrupt the comparison."""
    rows = _healthy_rows(10_000_000_000, 11_500_000_000, past_split_factor=0.0)
    assert _status(_evaluate(rows), R4) == "FAIL"
    rows = _healthy_rows(10_000_000_000, 11_500_000_000, past_split_factor=-2.0)
    assert _status(_evaluate(rows), R4) == "FAIL"


def test_rule_4_split_adjustment_no_red_flag():
    rows = _healthy_rows(5_750_000_000, 14_900_000_000, past_split_factor=4.0)
    res = _evaluate(rows)
    assert not any("Share count increased" in flag for flag in res.red_flags)


def test_rule_4_split_adjustment_updates_metric():
    rows = _healthy_rows(5_750_000_000, 14_900_000_000, past_split_factor=4.0)
    res = _evaluate(rows)
    # adjusted past = 5.75B * 4 = 23B -> change = 14.9/23 - 1 ≈ -0.352
    assert res.metrics["share_change_10y"] == pytest.approx(14.9 / 23.0 - 1.0)


def test_rule_4_split_adjustment_changes_verdict():
    """The AAPL shape flips from AVOID (dilution FAIL) to BUY once the 4:1
    split is restated and R&D/margins/cost-control all pass."""
    rows = _healthy_rows(5_750_000_000, 14_900_000_000, past_split_factor=4.0)
    assert _evaluate(rows).verdict == Verdict.BUY


# ---------------------------------------------------------------------------
# Fixtures carry expected overall shapes
# ---------------------------------------------------------------------------
def test_quality_fixture_all_four_pass():
    res = _evaluate(_fixture_rows("fisher_quant_quality.json"))
    assert _status(res, R1) == "PASS"
    assert _status(res, R2) == "PASS"
    assert _status(res, R3) == "PASS"
    assert _status(res, R4) == "PASS"


def test_weak_fixture_all_four_fail():
    res = _evaluate(_fixture_rows("fisher_quant_weak.json"))
    assert _status(res, R1) == "FAIL"
    assert _status(res, R2) == "FAIL"
    assert _status(res, R3) == "FAIL"
    assert _status(res, R4) == "FAIL"


def test_incomplete_fixture_shape():
    res = _evaluate(_fixture_rows("fisher_quant_incomplete.json"))
    assert _status(res, R1) == "INSUFFICIENT_DATA"
    assert _status(res, R2) == "PASS"
    assert _status(res, R3) == "INSUFFICIENT_DATA"
    assert _status(res, R4) == "INSUFFICIENT_DATA"


def test_3of4_fixture_watch_75():
    res = _evaluate(_fixture_rows("fisher_quant_3of4.json"))
    assert _status(res, R1) == "INSUFFICIENT_DATA"
    assert _status(res, R2) == "PASS"
    assert _status(res, R3) == "PASS"
    assert _status(res, R4) == "PASS"
    assert res.verdict == Verdict.WATCH
    assert res.score == pytest.approx(75.0)
    assert res.confidence == Confidence.MEDIUM


def test_perfect_fixture_buy_100():
    res = _evaluate(_fixture_rows("fisher_quant_perfect.json"))
    assert _status(res, R1) == "PASS"
    assert _status(res, R2) == "PASS"
    assert _status(res, R3) == "PASS"
    assert _status(res, R4) == "PASS"
    assert res.verdict == Verdict.BUY
    assert res.score == pytest.approx(100.0)
    assert res.confidence == Confidence.HIGH


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------
def test_verdict_buy_quality_fixture():
    res = _evaluate(_fixture_rows("fisher_quant_quality.json"))
    assert res.verdict == Verdict.BUY


def test_verdict_watch_three_pass_one_insufficient():
    """KO shape: R&D not reported, the other three rules pass -> WATCH (75)."""
    res = _evaluate(_ko_shape_rows())
    assert _status(res, R1) == "INSUFFICIENT_DATA"
    assert _status(res, R2) == "PASS"
    assert _status(res, R3) == "PASS"
    assert _status(res, R4) == "PASS"
    assert res.verdict == Verdict.WATCH
    assert res.score == pytest.approx(75.0)


def test_verdict_three_pass_one_watch_is_not_buy():
    """BUY requires 4/4: three PASS plus one WATCH stays WATCH, not BUY."""
    res = _evaluate(_healthy_rows(10_000_000_000, 10_500_000_000))
    assert _status(res, R1) == "PASS"
    assert _status(res, R4) == "WATCH"
    assert res.verdict == Verdict.WATCH


def test_verdict_hold_two_pass_no_fail():
    """P&G shape: modest R&D, strong margins, missing 10y shares -> HOLD (50)."""
    res = _evaluate(_full_margin_rows([0.42, 0.42, 0.425, 0.42, 0.42]))
    assert _status(res, R1) == "WATCH"
    assert _status(res, R2) == "PASS"
    assert _status(res, R3) == "PASS"
    assert _status(res, R4) == "INSUFFICIENT_DATA"
    assert res.verdict == Verdict.HOLD


def test_verdict_avoid_margin_fail():
    res = _evaluate(_healthy_rows(18_000_000_000, 15_000_000_000, net_ratio=0.04))
    assert _status(res, R2) == "FAIL"
    assert res.verdict == Verdict.AVOID


def test_verdict_avoid_dilution_fail():
    res = _evaluate(_healthy_rows(10_000_000_000, 11_500_000_000))
    assert _status(res, R4) == "FAIL"
    assert res.verdict == Verdict.AVOID


def test_verdict_avoid_any_fail_even_with_three_passes():
    """One FAIL vetoes the verdict even when the other three rules pass."""
    res = _evaluate(_healthy_rows(10_000_000_000, 10_500_000_000, net_ratio=0.04))
    assert _status(res, R2) == "FAIL"
    assert res.verdict == Verdict.AVOID


def test_verdict_avoids_fewer_than_two_passes():
    """Fewer than 2 PASS (no FAIL, not enough INSUFFICIENT) -> AVOID."""
    res = _evaluate(_full_margin_rows([0.55, 0.48, 0.57, 0.45, 0.50]))
    assert _status(res, R1) == "WATCH"
    assert _status(res, R3) == "WATCH"
    assert _status(res, R4) == "INSUFFICIENT_DATA"
    assert res.verdict == Verdict.AVOID


def test_verdict_insufficient_data_fixture():
    res = _evaluate(_fixture_rows("fisher_quant_incomplete.json"))
    assert res.verdict == Verdict.INSUFFICIENT_DATA


def test_verdict_empty_fundamentals():
    res = _evaluate([])
    assert res.verdict == Verdict.INSUFFICIENT_DATA
    assert res.score is None
    assert res.confidence == Confidence.LOW


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------
def test_score_quality_is_100():
    res = _evaluate(_fixture_rows("fisher_quant_quality.json"))
    assert res.score == pytest.approx(100.0)


def test_score_three_pass_one_insufficient_is_75():
    res = _evaluate(_ko_shape_rows())
    assert res.score == pytest.approx(75.0)


def test_score_hold_two_pass_is_50():
    res = _evaluate(_full_margin_rows([0.42, 0.42, 0.425, 0.42, 0.42]))
    assert res.verdict == Verdict.HOLD
    assert res.score == pytest.approx(50.0)


def test_score_none_when_insufficient_data_even_with_passes():
    res = _evaluate(_gross_margin_rows([0.42, 0.42, 0.42, 0.42, 0.42]))
    assert _status(res, R3) == "PASS"
    assert res.verdict == Verdict.INSUFFICIENT_DATA
    assert res.score is None


def test_score_none_weak_fixture_zero_pass():
    res = _evaluate(_fixture_rows("fisher_quant_weak.json"))
    assert res.score == pytest.approx(0.0)


def test_score_none_incomplete_fixture():
    res = _evaluate(_fixture_rows("fisher_quant_incomplete.json"))
    assert res.score is None


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------
def test_confidence_high_all_evaluated():
    res = _evaluate(_fixture_rows("fisher_quant_quality.json"))
    assert res.confidence == Confidence.HIGH


def test_confidence_medium_one_insufficient():
    res = _evaluate(_full_margin_rows([0.42, 0.42, 0.42, 0.42, 0.42]))
    assert res.confidence == Confidence.MEDIUM


def test_confidence_low_two_insufficient():
    res = _evaluate(_fixture_rows("fisher_quant_incomplete.json"))
    assert res.confidence == Confidence.LOW


# ---------------------------------------------------------------------------
# Red flags
# ---------------------------------------------------------------------------
def test_red_flag_rnd_below_2pct():
    res = _evaluate([_row(2024, 100_000_000_000, research_development=1_000_000_000)])
    assert "R&D below 2% of revenue without explanation" in res.red_flags


def test_red_flag_net_margin_below_5pct():
    res = _evaluate(
        [
            _row(
                2024,
                100_000_000_000,
                net_income=4_000_000_000,
                operating_income=20_000_000_000,
            )
        ]
    )
    assert "Net margin below 5%" in res.red_flags


def test_red_flag_gross_margin_volatile():
    res = _evaluate(_gross_margin_rows([0.70, 0.45, 0.60, 0.35, 0.55]))
    assert "Gross margin standard deviation above 5% over 5 years" in res.red_flags


def test_red_flag_share_dilution():
    res = _evaluate(_healthy_rows(10_000_000_000, 11_500_000_000))
    assert "Share count increased more than 10% over 10 years" in res.red_flags


def test_red_flags_weak_fixture_has_all_four():
    res = _evaluate(_fixture_rows("fisher_quant_weak.json"))
    assert len(res.red_flags) == 4


# ---------------------------------------------------------------------------
# Sources and rules
# ---------------------------------------------------------------------------
def test_sources_cite_fisher_1958():
    res = _evaluate(_fixture_rows("fisher_quant_quality.json"))
    assert len(res.sources) == 4
    for source in res.sources:
        assert source.book == "Common Stocks and Uncommon Profits"
        assert source.year == 1958
        assert source.era == "1958"


def test_source_pages_map_to_points():
    m = FisherQuantitativeSubsetMethodology()
    pages = [rule.source.page for rule in m.rules()]
    assert pages == ["54-55", "63-64", "69", "75"]


def test_rules_four_explicit_unique():
    m = FisherQuantitativeSubsetMethodology()
    rules = m.rules()
    assert len(rules) == 4
    assert all(rule.kind == "EXPLICIT" for rule in rules)
    assert len({rule.id for rule in rules}) == 4
    assert all(rule.id.startswith("fisher_quantitative_subset.") for rule in rules)


def test_metadata_subset_description():
    m = FisherQuantitativeSubsetMethodology()
    meta = m.metadata()
    assert meta["name"] == "fisher_quantitative_subset"
    assert meta["family"] == "QUALITY_COMPOUNDER"
    assert "subset" in meta["description"].lower()
    assert "11" in meta["description"]
    assert meta["source"]["year"] == 1958


# ---------------------------------------------------------------------------
# Determinism and hermeticity
# ---------------------------------------------------------------------------
def test_deterministic_output():
    rows = _fixture_rows("fisher_quant_quality.json")
    first = _evaluate(rows)
    second = _evaluate(rows)
    assert first.verdict == second.verdict
    assert first.score == second.score
    assert first.reasons == second.reasons
    assert first.red_flags == second.red_flags


def test_no_price_access():
    prices = _Prices()
    _evaluate(_fixture_rows("fisher_quant_quality.json"), prices)
    assert prices.calls == []


def test_no_network_or_db_imports():
    banned = ("yfinance", "requests", "urllib", "psycopg", "sqlalchemy", "socket")
    for name in ("rules.py", "methodology.py", "__init__.py"):
        text = (MODULE_DIR / name).read_text()
        for token in banned:
            assert token not in text, (name, token)


def test_readme_disclaimer_present():
    text = (MODULE_DIR / "README.md").read_text()
    assert "**This methodology is a quantitative SUBSET of Philip Fisher's 15" in text
    assert "It is NOT Fisher." in text
    assert "scuttlebutt" in text
    assert "docs/methodology_decisions.md" in text


# ---------------------------------------------------------------------------
# financial companies (banks/insurers are out of scope; the shared company-type
# detector guards before any rule runs)
# ---------------------------------------------------------------------------
def test_financial_company_not_applicable():
    rows = [
        NormalizedFinancials.from_dict(
            {
                "ticker": "T",
                "fiscal_year": 2024,
                "period": "FY",
                "revenue": 30e9,
                "net_income": 8e9,
                "operating_cash_flow": -10e9,
            }
        )
    ]
    result = FisherQuantitativeSubsetMethodology().evaluate("T", rows, _Prices())
    assert result.verdict == Verdict.NOT_APPLICABLE
    assert result.score is None
    assert result.confidence == Confidence.HIGH
    assert result.metrics["financial_company"] is True
    assert result.failed_rules == []
    assert any("financial" in r.lower() for r in result.reasons)


def test_financial_sector_hint_not_applicable():
    rows = [
        NormalizedFinancials.from_dict(
            {
                "ticker": "T",
                "fiscal_year": 2024,
                "period": "FY",
                "revenue": 30e9,
                "net_income": 8e9,
                "sector": "Financial Services",
            }
        )
    ]
    result = FisherQuantitativeSubsetMethodology().evaluate("T", rows, _Prices())
    assert result.verdict == Verdict.NOT_APPLICABLE
    assert result.metrics["financial_company"] is True
