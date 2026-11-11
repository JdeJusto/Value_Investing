"""Unit tests for the deep Buffett/Clark weighted checks.

Hermetic: rows are built in memory; no network, database or randomness. Each
deep rule gets a pass and a fail fixture; the weighted thresholds are tested on
constructed outcomes.
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)
from backend.methodologies.buffett_clark.deep_checks import CHECKS, CHECKS_BY_ID
from backend.methodologies.common.weighted import WeightedResult, weighted_verdict


class _Dcf:
    def __init__(self, margin, intrinsic=200.0):
        self.margin_of_safety = margin
        self.intrinsic_value_per_share = intrinsic


class _Prices:
    """Historical-price stub returning one constant fiscal-year-end price."""

    def __init__(self, past_price=20.0):
        self.past_price = past_price
        self.calls = []

    def get_price_at_fiscal_year_end(self, ticker, fiscal_year, end=None):
        self.calls.append((ticker, fiscal_year))
        return self.past_price


def _row(year, **overrides):
    data = {
        "revenue": 100e9,
        "gross_profit": 45e9,
        "operating_income": 20e9,
        "ebit": 20e9,
        "net_income": 12e9,
        "interest_expense": 0.0,
        "tax_provision": 2.5e9,
        "pretax_income": 15e9,
        "total_debt": 10e9,
        "stockholders_equity": 50e9,
        "cash_and_equivalents": 10e9,
        "capital_expenditure": 1.2e9,
        "depreciation_amortization": 5e9,
        "operating_cash_flow": 15e9,
        "free_cash_flow": 13.8e9,
        "retained_earnings": 40e9,
        "repurchase_of_stock": 0.0,
        "shares_outstanding": 1_000_000_000,
        "period": "FY",
        "source": ProviderName.EDGAR,
    }
    data.update(overrides)
    return NormalizedFinancials(ticker="TEST", fiscal_year=year, **data)


def _flat(count=11, newest=2024, **overrides):
    return [_row(newest - index, **overrides) for index in range(count)]


def _check(rule_id, rows, price=None, dcf=None, prices=None, ticker="TEST"):
    return CHECKS_BY_ID[rule_id].evaluate(rows, price, dcf, prices, ticker)


# ---------------------------------------------------------------------------
# durable advantage
# ---------------------------------------------------------------------------
def test_roic_current_pass_and_fail():
    assert _check("buffett_clark.deep_roic_current", _flat(1)).passed is True
    assert _check("buffett_clark.deep_roic_current", _flat(1, ebit=5e9)).passed is False


def test_roic_5y_pass_and_fail():
    rows = _flat(5)
    assert _check("buffett_clark.deep_roic_5y", rows).passed is True
    rows[2] = _row(2022, ebit=5e9)
    assert _check("buffett_clark.deep_roic_5y", rows).passed is False
    # fewer than five years is a data gap, not a failure
    assert _check("buffett_clark.deep_roic_5y", _flat(3)).passed is None


def test_roe_15_pass_and_fail():
    assert _check("buffett_clark.deep_roe_15", _flat(1)).passed is True
    assert _check("buffett_clark.deep_roe_15", _flat(1, net_income=5e9)).passed is False


def test_low_capex_pass_and_fail():
    assert _check("buffett_clark.deep_low_capex", _flat(1)).passed is True
    assert (
        _check("buffett_clark.deep_low_capex", _flat(1, capital_expenditure=5e9)).passed
        is False
    )


def test_predictable_earnings_pass_and_fail():
    assert _check("buffett_clark.deep_predictable_earnings", _flat(10)).passed is True
    choppy = [
        _row(2024 - index, net_income=(12e9 if index % 2 == 0 else 6e9))
        for index in range(10)
    ]
    assert _check("buffett_clark.deep_predictable_earnings", choppy).passed is False


def test_low_debt_pass_and_fail():
    assert _check("buffett_clark.deep_low_debt", _flat(1)).passed is True
    assert (
        _check("buffett_clark.deep_low_debt", _flat(1, total_debt=40e9)).passed is False
    )
    # long-term debt takes precedence when reported
    assert (
        _check(
            "buffett_clark.deep_low_debt",
            _flat(1, long_term_debt=5e9, total_debt=40e9),
        ).passed
        is True
    )


def test_gross_margin_stability_pass_and_fail():
    stable = [_row(2024 - index, gross_profit=0.45 * 100e9) for index in range(5)]
    volatile = [
        _row(2024 - index, gross_profit=margin * 100e9)
        for index, margin in enumerate([0.45, 0.30, 0.50, 0.28, 0.47])
    ]
    assert _check("buffett_clark.deep_gross_margin_stability", stable).passed is True
    assert _check("buffett_clark.deep_gross_margin_stability", volatile).passed is False


# ---------------------------------------------------------------------------
# owner earnings
# ---------------------------------------------------------------------------
def test_owner_earnings_positive_pass_and_fail():
    assert _check("buffett_clark.deep_owner_earnings_positive", _flat(1)).passed is True
    assert (
        _check(
            "buffett_clark.deep_owner_earnings_positive",
            _flat(1, capital_expenditure=20e9),
        ).passed
        is False
    )


def test_owner_earnings_growing_pass_and_fail():
    growing = [
        _row(2024 - index, net_income=10e9 + (4 - index) * 1e9) for index in range(5)
    ]
    shrinking = [
        _row(2024 - index, net_income=10e9 + index * 1e9) for index in range(5)
    ]
    assert _check("buffett_clark.deep_owner_earnings_growing", growing).passed is True
    assert (
        _check("buffett_clark.deep_owner_earnings_growing", shrinking).passed is False
    )


def test_bvps_growth_pass_and_fail():
    growing = [
        _row(2024 - index, stockholders_equity=50e9 * (1.12 ** (10 - index)))
        for index in range(11)
    ]
    flat = _flat(11)
    assert _check("buffett_clark.deep_bvps_growth_10y", growing).passed is True
    assert _check("buffett_clark.deep_bvps_growth_10y", flat).passed is False


# ---------------------------------------------------------------------------
# valuation
# ---------------------------------------------------------------------------
def test_dcf_margin_of_safety_pass_and_fail():
    rows = _flat(1)
    assert (
        _check(
            "buffett_clark.deep_dcf_margin_of_safety_50",
            rows,
            price=100.0,
            dcf=_Dcf(0.60),
        ).passed
        is True
    )
    assert (
        _check(
            "buffett_clark.deep_dcf_margin_of_safety_50",
            rows,
            price=100.0,
            dcf=_Dcf(0.30),
        ).passed
        is False
    )
    assert (
        _check(
            "buffett_clark.deep_dcf_margin_of_safety_50",
            rows,
            price=100.0,
            dcf=None,
        ).passed
        is None
    )


def test_pe_below_20_pass_and_fail():
    assert (
        _check("buffett_clark.deep_pe_below_20", _flat(3), price=100.0).passed is True
    )
    assert (
        _check("buffett_clark.deep_pe_below_20", _flat(3), price=300.0).passed is False
    )


def test_pe_below_5y_average_pass_and_fail():
    rows = _flat(6)
    prices = _Prices(past_price=20.0)
    assert (
        _check(
            "buffett_clark.deep_pe_below_5y_average",
            rows,
            price=10.0,
            prices=prices,
            ticker="TEST",
        ).passed
        is True
    )
    assert (
        _check(
            "buffett_clark.deep_pe_below_5y_average",
            rows,
            price=30.0,
            prices=prices,
            ticker="TEST",
        ).passed
        is False
    )


def test_pe_below_5y_average_degrades_without_price_history():
    rows = _flat(6)
    assert (
        _check("buffett_clark.deep_pe_below_5y_average", rows, price=10.0).passed
        is None
    )


# ---------------------------------------------------------------------------
# growth
# ---------------------------------------------------------------------------
def test_revenue_cagr_pass_and_fail():
    growing = [
        _row(2024 - index, revenue=100e9 * (1.06 ** (10 - index)))
        for index in range(11)
    ]
    assert _check("buffett_clark.deep_revenue_cagr_5", growing).passed is True
    assert _check("buffett_clark.deep_revenue_cagr_5", _flat(11)).passed is False


def test_eps_cagr_pass_and_fail():
    growing = [
        _row(2024 - index, net_income=12e9 * (1.12 ** (10 - index)))
        for index in range(11)
    ]
    assert _check("buffett_clark.deep_eps_cagr_10", growing).passed is True
    assert _check("buffett_clark.deep_eps_cagr_10", _flat(11)).passed is False


def test_positive_earnings_pass_and_fail():
    assert _check("buffett_clark.deep_positive_earnings_10y", _flat(10)).passed is True
    rows = _flat(10)
    rows[4] = _row(2020, net_income=-1e9)
    assert _check("buffett_clark.deep_positive_earnings_10y", rows).passed is False


# ---------------------------------------------------------------------------
# registry and framework
# ---------------------------------------------------------------------------
def test_all_deep_checks_are_registered():
    results = [_row(2024)]
    evaluated = [check.evaluate(results, None, None, None, None) for check in CHECKS]
    assert len(CHECKS) == 16
    assert len({item.rule_id for item in evaluated}) == 16
    assert all(item.weight in (0, 1, 2) for item in evaluated)


def test_duplicate_rule_ids_are_not_registered():
    ids = [check.rule_id for check in CHECKS]
    assert len(ids) == len(set(ids))
    assert all(rule_id.startswith("buffett_clark.deep_") for rule_id in ids)


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
            WeightedResult(
                rule_id=f"r{index}",
                name="r",
                category="c",
                weight=1,
                passed=True,
                detail="",
            )
            for index in range(passed)
        ] + [
            WeightedResult(
                rule_id=f"f{index}",
                name="f",
                category="c",
                weight=1,
                passed=False,
                detail="",
            )
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
