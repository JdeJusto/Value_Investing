"""Unit tests for the deep Fisher weighted checks.

Hermetic: rows are built in memory; no network, database, price lookup or
randomness. Each deep rule gets a pass and a fail fixture; the weighted
thresholds are tested on constructed outcomes.
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)
from backend.methodologies.common.weighted import WeightedResult, weighted_verdict
from backend.methodologies.fisher_quantitative_subset.deep_checks import (
    CHECKS,
    CHECKS_BY_ID,
)


def _row(year, **overrides):
    data = {
        "revenue": 100e9,
        "gross_profit": 45e9,
        "operating_income": 25e9,
        "ebit": 25e9,
        "net_income": 20e9,
        "tax_provision": 4e9,
        "pretax_income": 24e9,
        "sga": 20e9,
        "research_development": 9e9,
        "total_debt": 5e9,
        "stockholders_equity": 80e9,
        "cash_and_equivalents": 10e9,
        "operating_cash_flow": 30e9,
        "capital_expenditure": 5e9,
        "free_cash_flow": 25e9,
        "shares_outstanding": 1_000_000_000,
        "repurchase_of_stock": 1e9,
        "period": "FY",
        "source": ProviderName.EDGAR,
    }
    data.update(overrides)
    return NormalizedFinancials(ticker="TEST", fiscal_year=year, **data)


def _flat(count=6, newest=2024, **overrides):
    return [_row(newest - index, **overrides) for index in range(count)]


def _check(rule_id, rows, sector=None):
    return CHECKS_BY_ID[rule_id].evaluate(rows, None, sector)


# ---------------------------------------------------------------------------
# growth potential
# ---------------------------------------------------------------------------
def test_revenue_growth_pass_and_fail():
    pass_rows = [_row(2024, revenue=120e9), _row(2023, revenue=100e9)]
    fail_rows = [_row(2024, revenue=110e9), _row(2023, revenue=100e9)]
    assert (
        _check("fisher_quantitative_subset.deep_revenue_growth_15", pass_rows).passed
        is True
    )
    assert (
        _check("fisher_quantitative_subset.deep_revenue_growth_15", fail_rows).passed
        is False
    )


def test_revenue_growth_consistent_pass_and_fail():
    growing = [
        _row(2024 - index, revenue=100e9 * (1.12 ** (5 - index))) for index in range(6)
    ]
    flat = _flat(6)
    assert (
        _check(
            "fisher_quantitative_subset.deep_revenue_growth_consistent_5y", growing
        ).passed
        is True
    )
    assert (
        _check(
            "fisher_quantitative_subset.deep_revenue_growth_consistent_5y", flat
        ).passed
        is False
    )


def test_rnd_intensity_pass_and_fail():
    assert (
        _check(
            "fisher_quantitative_subset.deep_rnd_intensity",
            [_row(2024, research_development=9e9)],
        ).passed
        is True
    )
    assert (
        _check(
            "fisher_quantitative_subset.deep_rnd_intensity",
            [_row(2024, research_development=1e9)],
        ).passed
        is False
    )
    # Unknown sector with no R&D is a data gap, not a failure.
    assert (
        _check(
            "fisher_quantitative_subset.deep_rnd_intensity",
            [_row(2024, research_development=None)],
        ).passed
        is None
    )


# ---------------------------------------------------------------------------
# profitability
# ---------------------------------------------------------------------------
def test_net_margin_pass_and_fail():
    assert (
        _check("fisher_quantitative_subset.deep_net_margin_15", [_row(2024)]).passed
        is True
    )
    assert (
        _check(
            "fisher_quantitative_subset.deep_net_margin_15",
            [_row(2024, net_income=10e9)],
        ).passed
        is False
    )


def test_margin_improvement_pass_and_fail():
    improving = [
        _row(2024, net_income=20e9),
        _row(2023, net_income=18e9),
        _row(2022, net_income=15e9),
    ]
    flat = _flat(3, net_income=18e9)
    assert (
        _check("fisher_quantitative_subset.deep_margin_improvement", improving).passed
        is True
    )
    assert (
        _check("fisher_quantitative_subset.deep_margin_improvement", flat).passed
        is False
    )


def test_gross_margin_pass_and_fail():
    assert (
        _check("fisher_quantitative_subset.deep_gross_margin_40", [_row(2024)]).passed
        is True
    )
    assert (
        _check(
            "fisher_quantitative_subset.deep_gross_margin_40",
            [_row(2024, gross_profit=30e9)],
        ).passed
        is False
    )


# ---------------------------------------------------------------------------
# cost efficiency
# ---------------------------------------------------------------------------
def test_sga_ratio_stable_pass_and_fail():
    stable = _flat(5, sga=20e9)
    volatile = [
        _row(2024 - index, sga=sga * 100e9)
        for index, sga in enumerate([0.10, 0.30, 0.15, 0.28, 0.12])
    ]
    assert (
        _check("fisher_quantitative_subset.deep_sga_ratio_stable", stable).passed
        is True
    )
    assert (
        _check("fisher_quantitative_subset.deep_sga_ratio_stable", volatile).passed
        is False
    )


def test_operating_leverage_pass_and_fail():
    leveraged = [
        _row(2024 - index, operating_income=25e9 * (1.15 ** (4 - index)))
        for index in range(5)
    ]
    deleveraged = [
        _row(2024 - index, operating_income=25e9 * (1.05 ** (4 - index)))
        for index in range(5)
    ]
    # Revenue grows 12%/year (oldest -> newest) in both cases.
    for index, row in enumerate(leveraged):
        row.revenue = 100e9 * (1.12 ** (4 - index))
    for index, row in enumerate(deleveraged):
        row.revenue = 100e9 * (1.12 ** (4 - index))
    assert (
        _check("fisher_quantitative_subset.deep_operating_leverage", leveraged).passed
        is True
    )
    assert (
        _check("fisher_quantitative_subset.deep_operating_leverage", deleveraged).passed
        is False
    )


# ---------------------------------------------------------------------------
# capital discipline
# ---------------------------------------------------------------------------
def test_no_dilution_pass_and_fail():
    flat = _flat(6, shares_outstanding=1_000_000_000)
    diluted = [
        _row(
            2024 - index,
            shares_outstanding=1_000_000_000 if index == 0 else 900_000_000,
        )
        for index in range(6)
    ]
    assert _check("fisher_quantitative_subset.deep_no_dilution_5y", flat).passed is True
    assert (
        _check("fisher_quantitative_subset.deep_no_dilution_5y", diluted).passed
        is False
    )


def test_buybacks_pass_and_fail():
    buying = [
        _row(
            2024 - index,
            shares_outstanding=1_000_000_000 - (5 - index) * 10_000_000,
        )
        for index in range(6)
    ]
    issuing = [
        _row(
            2024 - index,
            shares_outstanding=1_000_000_000 + (5 - index) * 10_000_000,
            repurchase_of_stock=0.0,
        )
        for index in range(6)
    ]
    assert (
        _check("fisher_quantitative_subset.deep_buybacks_3_of_5y", buying).passed
        is True
    )
    assert (
        _check("fisher_quantitative_subset.deep_buybacks_3_of_5y", issuing).passed
        is False
    )


def test_fcf_positive_pass_and_fail():
    assert (
        _check("fisher_quantitative_subset.deep_fcf_positive_5y", _flat(5)).passed
        is True
    )
    rows = _flat(5)
    rows[2] = _row(2022, free_cash_flow=-1e9, operating_cash_flow=4e9)
    assert (
        _check("fisher_quantitative_subset.deep_fcf_positive_5y", rows).passed is False
    )


def test_roic_pass_and_fail():
    assert (
        _check("fisher_quantitative_subset.deep_roic_15", [_row(2024)]).passed is True
    )
    assert (
        _check("fisher_quantitative_subset.deep_roic_15", [_row(2024, ebit=5e9)]).passed
        is False
    )


def test_rnd_growth_pace_pass_and_fail():
    keeping_pace = [
        _row(2024 - index, research_development=9e9 * (1.12 ** (3 - index)))
        for index in range(4)
    ]
    for index, row in enumerate(keeping_pace):
        row.revenue = 100e9 * (1.12 ** (3 - index))
    falling_behind = [
        _row(2024 - index, research_development=9e9) for index in range(4)
    ]
    for index, row in enumerate(falling_behind):
        row.revenue = 100e9 * (1.12 ** (3 - index))
    assert (
        _check("fisher_quantitative_subset.deep_rnd_growth_pace", keeping_pace).passed
        is True
    )
    assert (
        _check("fisher_quantitative_subset.deep_rnd_growth_pace", falling_behind).passed
        is False
    )


# ---------------------------------------------------------------------------
# registry and framework
# ---------------------------------------------------------------------------
def test_all_deep_checks_are_registered():
    evaluated = [check.evaluate([_row(2024)], None, None) for check in CHECKS]
    assert len(CHECKS) == 13
    assert len({item.rule_id for item in evaluated}) == 13
    assert all(item.weight in (0, 1, 2) for item in evaluated)


def test_duplicate_rule_ids_are_not_registered():
    ids = [check.rule_id for check in CHECKS]
    assert len(ids) == len(set(ids))
    assert all(
        rule_id.startswith("fisher_quantitative_subset.deep_") for rule_id in ids
    )


def test_weighted_verdict_thresholds():
    cases = [
        (0.90, "BUY"),
        (0.85, "BUY"),
        (0.80, "WATCH"),
        (0.70, "WATCH"),
        (0.60, "HOLD"),
        (0.50, "HOLD"),
        (0.40, "AVOID"),
    ]
    for ratio, expected in cases:
        passed = round(ratio * 100)
        results = [
            WeightedResult(f"r{index}", "r", "c", 1, True, "")
            for index in range(passed)
        ] + [
            WeightedResult(f"f{index}", "f", "c", 1, False, "")
            for index in range(100 - passed)
        ]
        verdict, score, _confidence = weighted_verdict(results)
        assert verdict.value == expected, ratio
        assert score == round(ratio * 100, 2)


def test_missing_weight_above_30pct_is_insufficient():
    results = [
        WeightedResult("a", "a", "c", 2, True, ""),
        WeightedResult("b", "b", "c", 2, None, ""),
        WeightedResult("c", "c", "c", 2, None, ""),
    ]
    verdict, score, confidence = weighted_verdict(results)
    assert verdict.value == "INSUFFICIENT_DATA"
    assert score is None
    assert confidence.value == "LOW"


def test_informational_rules_do_not_enter_the_denominator():
    results = [
        WeightedResult("a", "a", "c", 2, True, ""),
        WeightedResult("b", "b", "c", 2, False, ""),
        WeightedResult("info", "info", "c", 0, False, ""),
    ]
    verdict, score, _confidence = weighted_verdict(results)
    assert verdict.value == "HOLD"
    assert score == 50.0
