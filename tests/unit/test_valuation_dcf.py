"""Hermetic tests for the ``not-from-canon`` DCF valuation module.

No network, no database, no prices persisted: ``fundamentals`` are fixture
rows and ``price_service`` is a stub that raises if the module reaches for
anything beyond ``get_current_price`` / ``get_market_cap`` / ``get_beta``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.valuation.base import SOURCE, DCFAssumptions, DCFResult
from backend.valuation.dcf import INSUFFICIENT_DATA, DCFValuation

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
VALUATION_DIR = Path(__file__).resolve().parents[2] / "backend" / "valuation"


class _Prices:
    """Read-only stub that fails loudly if the DCF reaches beyond 3 reads."""

    def __init__(self, price=340.0, market_cap=3_300_000_000_000.0, beta=1.15):
        self._price = price
        self._market_cap = market_cap
        self._beta = beta
        self.calls = []
        self._persisted = False

    def get_current_price(self, ticker):
        self.calls.append(("current_price", ticker))
        return self._price

    def get_market_cap(self, ticker):
        self.calls.append(("market_cap", ticker))
        return self._market_cap

    def get_beta(self, ticker):
        self.calls.append(("beta", ticker))
        return self._beta

    def __getattr__(self, name):
        raise AssertionError(
            f"DCF reached for unexpected price-service method {name!r}"
        )


def _row(year, **kwargs):
    data = {
        "ticker": "TEST",
        "fiscal_year": year,
        "period": "FY",
        "currency": "USD",
        "source": "sec_edgar",
    }
    data.update(kwargs)
    return NormalizedFinancials.from_dict(data)


def _fixture_rows(name):
    raw = json.loads((FIXTURES / name).read_text())
    return [NormalizedFinancials.from_dict(r) for r in raw]


def _evaluate(
    rows,
    *,
    price=340.0,
    market_cap=3_300_000_000_000.0,
    beta=1.15,
    assumptions=None,
):
    stub = _Prices(price=price, market_cap=market_cap, beta=beta)
    result = DCFValuation(assumptions).evaluate("TEST", rows, stub)
    return result, stub


def _aapl_rows():
    return _fixture_rows("dcf_aapl_like.json")


# ---------------------------------------------------------------------------
# happy path + inputs
# ---------------------------------------------------------------------------
def test_positive_fcf_produces_value():
    result, _ = _evaluate(_aapl_rows())
    assert result.verdict != INSUFFICIENT_DATA
    assert result.intrinsic_value_per_share is not None
    assert result.intrinsic_value_per_share > 0
    assert result.margin_of_safety is not None


def test_fcf_base_is_three_year_average():
    result, _ = _evaluate(_aapl_rows())
    expected = (108.9e9 + 99.4e9 + 111.5e9) / 3
    assert result.fcf_years == 3
    assert result.fcf_base == pytest.approx(expected)


def test_fcf_latest_year_fallback():
    rows = [
        _row(
            2024,
            revenue=100e9,
            operating_cash_flow=100e9,
            capital_expenditure=10e9,
            shares_outstanding=1e9,
        ),
        _row(2023, revenue=90e9, shares_outstanding=1e9),
    ]
    result, _ = _evaluate(rows)
    assert result.fcf_years == 1
    assert result.fcf_base == pytest.approx(90e9)


def test_negative_fcf_insufficient():
    result, stub = _evaluate(_fixture_rows("dcf_negative_fcf.json"))
    assert result.verdict == INSUFFICIENT_DATA
    assert result.intrinsic_value_per_share is None
    joined = " ".join(result.reasons).lower()
    assert "negative fcf" in joined
    assert "cash-burning" in joined
    assert "positive free cash flow" in result.missing_inputs
    # No price lookups happen before the negative-FCF guard.
    assert stub.calls == []


def test_missing_shares_insufficient():
    rows = _aapl_rows()
    rows[0].shares_outstanding = None
    result, _ = _evaluate(rows)
    assert result.verdict == INSUFFICIENT_DATA
    assert "shares outstanding" in result.missing_inputs


def test_no_fundamentals_insufficient():
    result, _ = _evaluate([])
    assert result.verdict == INSUFFICIENT_DATA
    assert any("No fundamentals" in r for r in result.reasons)


def test_missing_price_insufficient():
    result, _ = _evaluate(_aapl_rows(), price=None)
    assert result.verdict == INSUFFICIENT_DATA
    assert "current price" in result.missing_inputs


# ---------------------------------------------------------------------------
# WACC guards and overrides
# ---------------------------------------------------------------------------
def test_wacc_below_terminal_insufficient():
    assumptions = DCFAssumptions(wacc_override=0.02, terminal_growth=0.025)
    result, _ = _evaluate(_aapl_rows(), assumptions=assumptions)
    assert result.verdict == INSUFFICIENT_DATA
    joined = " ".join(result.reasons)
    assert "WACC" in joined and "terminal growth" in joined
    assert "wacc > terminal growth" in result.missing_inputs


def test_growth_override_respected():
    assumptions = DCFAssumptions(growth_override=0.08)
    result, _ = _evaluate(_aapl_rows(), assumptions=assumptions)
    assert result.growth_1_5 == 0.08
    assert result.growth_6_10 == 0.04
    assert any("overridden" in r for r in result.reasons)


def test_wacc_beta_fallback_to_one():
    rows = [
        _row(
            2024,
            revenue=100e9,
            operating_cash_flow=30e9,
            capital_expenditure=5e9,
            shares_outstanding=1e9,
            stockholders_equity=100e9,
        ),
        _row(
            2023,
            revenue=90e9,
            operating_cash_flow=30e9,
            capital_expenditure=5e9,
            shares_outstanding=1e9,
        ),
        _row(
            2022,
            revenue=80e9,
            operating_cash_flow=30e9,
            capital_expenditure=5e9,
            shares_outstanding=1e9,
        ),
        _row(
            2021,
            revenue=70e9,
            operating_cash_flow=30e9,
            capital_expenditure=5e9,
            shares_outstanding=1e9,
        ),
        _row(
            2020,
            revenue=60e9,
            operating_cash_flow=30e9,
            capital_expenditure=5e9,
            shares_outstanding=1e9,
        ),
    ]
    result, _ = _evaluate(rows, market_cap=500e9, beta=None)
    # No debt -> all-equity; beta fallback -> CoE = 4% + 1.0 * 5% = 9%.
    assert result.wacc == pytest.approx(0.09)
    assert any("assumed 1.0" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# verdicts
# ---------------------------------------------------------------------------
def _intrinsic_for(rows, **kwargs):
    result, _ = _evaluate(rows, **kwargs)
    assert result.intrinsic_value_per_share is not None
    return result.intrinsic_value_per_share


def test_verdict_undervalued():
    rows = _aapl_rows()
    value = _intrinsic_for(rows)
    result, _ = _evaluate(rows, price=value * 0.5)
    assert result.verdict == "UNDERVALUED"
    assert result.margin_of_safety >= 0.25


def test_verdict_fair():
    rows = _aapl_rows()
    value = _intrinsic_for(rows)
    result, _ = _evaluate(rows, price=value * 0.9)
    assert result.verdict == "FAIR"
    assert -0.10 < result.margin_of_safety < 0.25


def test_verdict_overvalued():
    rows = _aapl_rows()
    value = _intrinsic_for(rows)
    result, _ = _evaluate(rows, price=value * 2.0)
    assert result.verdict == "OVERVALUED"
    assert result.margin_of_safety <= -0.10


def test_margin_of_safety_capped_at_minus_ten():
    rows = _aapl_rows()
    value = _intrinsic_for(rows)
    result, _ = _evaluate(rows, price=value * 12.0)
    assert result.margin_of_safety == -10.0
    assert result.verdict == "OVERVALUED"


# ---------------------------------------------------------------------------
# growth caps
# ---------------------------------------------------------------------------
def test_growth_caps_enforced():
    rows = [
        _row(
            y,
            revenue=rev,
            operating_cash_flow=120e9,
            capital_expenditure=20e9,
            shares_outstanding=10e9,
        )
        for y, rev in zip(
            range(2024, 2018, -1),
            [2000e9, 900e9, 450e9, 250e9, 150e9, 100e9],
        )
    ]
    result, _ = _evaluate(rows)
    assert result.growth_1_5 == 0.20  # capped at max_growth_years_1_5
    assert result.growth_6_10 == 0.10  # capped at max_growth_years_6_10


def test_negative_revenue_cagr_keeps_positive_fcf_value():
    rows = [
        _row(
            y,
            revenue=rev,
            operating_cash_flow=40e9,
            capital_expenditure=5e9,
            shares_outstanding=10e9,
            total_debt=100e9,
            interest_expense=5e9,
            stockholders_equity=50e9,
        )
        for y, rev in zip(
            range(2024, 2018, -1),
            [50e9, 60e9, 70e9, 80e9, 90e9, 100e9],
        )
    ]
    result, _ = _evaluate(rows, market_cap=100e9)
    assert result.verdict != INSUFFICIENT_DATA
    assert result.growth_1_5 < 0
    assert result.intrinsic_value_per_share is not None


# ---------------------------------------------------------------------------
# terminal value sanity
# ---------------------------------------------------------------------------
def test_terminal_value_sane_when_wacc_near_terminal():
    assumptions = DCFAssumptions(wacc_override=0.041, terminal_growth=0.04)
    result, _ = _evaluate(_aapl_rows(), assumptions=assumptions)
    assert result.verdict != INSUFFICIENT_DATA
    assert result.intrinsic_value_per_share is not None
    assert math.isfinite(result.intrinsic_value_per_share)


def test_wacc_equal_terminal_is_insufficient():
    assumptions = DCFAssumptions(wacc_override=0.04, terminal_growth=0.04)
    result, _ = _evaluate(_aapl_rows(), assumptions=assumptions)
    assert result.verdict == INSUFFICIENT_DATA
    assert "wacc > terminal growth" in result.missing_inputs


# ---------------------------------------------------------------------------
# sensitivity
# ---------------------------------------------------------------------------
def test_sensitivity_has_nine_cells():
    result, _ = _evaluate(_aapl_rows())
    assert len(result.sensitivity) == 9
    for key, value in result.sensitivity.items():
        assert isinstance(key, tuple) and len(key) == 2
        assert all(isinstance(k, float) for k in key)
        assert value is None or isinstance(value, float)


def test_sensitivity_center_matches_intrinsic():
    result, _ = _evaluate(_aapl_rows())
    center = result.sensitivity[(result.wacc, result.growth_1_5)]
    assert center == pytest.approx(result.intrinsic_value_per_share)


# ---------------------------------------------------------------------------
# determinism / hermeticity / labels
# ---------------------------------------------------------------------------
def test_deterministic_across_runs():
    rows = _aapl_rows()
    first, _ = _evaluate(rows)
    second, _ = _evaluate(_fixture_rows("dcf_aapl_like.json"))
    assert first.intrinsic_value_per_share == second.intrinsic_value_per_share
    assert first.sensitivity == second.sensitivity
    assert first.margin_of_safety == second.margin_of_safety


def test_only_read_price_methods_used_and_nothing_persisted():
    rows = _aapl_rows()
    _, stub = _evaluate(rows)
    names = {name for name, _ in stub.calls}
    assert names == {"current_price", "market_cap", "beta"}
    assert stub._persisted is False  # nothing written by the module


def test_result_carries_not_from_canon_source():
    result, _ = _evaluate(_aapl_rows())
    assert result.source == SOURCE == "not-from-canon"
    assert (
        DCFResult(
            ticker="X",
            intrinsic_value_per_share=None,
            current_price=None,
            margin_of_safety=None,
            verdict="x",
            wacc=None,
            fcf_base=None,
            fcf_years=None,
            growth_1_5=None,
            growth_6_10=None,
            terminal_growth=0.025,
            shares_outstanding=None,
        ).source
        == SOURCE
    )


def test_readme_carries_not_from_canon_disclaimer():
    text = (VALUATION_DIR / "README.md").read_text()
    assert "not-from-canon" in text
    assert "NOT part of any book-derived methodology" in text


# ---------------------------------------------------------------------------
# financials (now a dividend discount model variant)
# ---------------------------------------------------------------------------
def test_financial_company_insufficient():
    # Banks/insurers have no free cash flow in the DCF sense, so they route
    # to the ddm_financial variant; with no dividends paid the DDM cannot be
    # computed and reads INSUFFICIENT_DATA rather than fabricating a value.
    result, _ = _evaluate(_fixture_rows("dcf_financial_company.json"))
    assert result.verdict == INSUFFICIENT_DATA
    joined = " ".join(result.reasons)
    assert "Financial company" in joined
    assert "banks/insurers" in joined
    assert result.missing_inputs == ["dividends per share"]
    assert result.variant == "ddm_financial"
    assert result.intrinsic_value_per_share is None


def test_financial_bank_without_interest_signal_insufficient():
    # JPM-like fingerprint: revenue + positive net income, but non-positive
    # operating cash flow and no capex (leaves no FCF to discount in any
    # reading). Routes to the DDM variant, which still needs a dividend
    # stream the rows do not carry.
    rows = [
        _row(
            2025,
            revenue=182e9,
            net_income=55.7e9,
            operating_cash_flow=-147.8e9,
            shares_outstanding=2.78e9,
        ),
        _row(
            2024,
            revenue=167e9,
            net_income=50e9,
            operating_cash_flow=-90e9,
            shares_outstanding=2.9e9,
        ),
    ]
    result, _ = _evaluate(rows)
    assert result.verdict == INSUFFICIENT_DATA
    joined = " ".join(result.reasons)
    assert "Financial company" in joined
    assert "banks/insurers" in joined
    assert result.missing_inputs == ["dividends per share"]
    assert result.variant == "ddm_financial"
    assert result.intrinsic_value_per_share is None


def test_financial_with_dividends_uses_two_stage_ddm():
    # Same JPM-like shape, but a real dividend stream: the two-stage DDM runs
    # and produces a priced verdict instead of bailing. A single-stage Gordon
    # would be undefined whenever dividend growth exceeds the cost of equity;
    # the two-stage model stays defined.
    rows = [
        _row(
            2025,
            revenue=182e9,
            net_income=55.7e9,
            operating_cash_flow=-147.8e9,
            shares_outstanding=2.78e9,
            dividends_paid=12e9,
        ),
        _row(
            2024,
            revenue=167e9,
            net_income=50e9,
            operating_cash_flow=-90e9,
            shares_outstanding=2.9e9,
            dividends_paid=11.6e9,
        ),
        _row(
            2023,
            revenue=155e9,
            net_income=48e9,
            operating_cash_flow=-80e9,
            shares_outstanding=2.95e9,
            dividends_paid=11.2e9,
        ),
    ]
    result, _ = _evaluate(rows, beta=1.0)
    assert result.verdict != INSUFFICIENT_DATA
    assert result.variant == "ddm_financial_two_stage"
    assert result.intrinsic_value_per_share is not None
    # dps 2025 = 12e9/2.78e9; dps 2023 = 11.2e9/2.95e9; CAGR over 2 years.
    dps_2025 = 12e9 / 2.78e9
    dps_2023 = 11.2e9 / 2.95e9
    g1 = (dps_2025 / dps_2023) ** 0.5 - 1.0
    assert result.growth_1_5 == pytest.approx(g1)
    assert result.wacc == pytest.approx(0.09)
    # Two-stage: 10 years at g1, then a Gordon terminal at 2.5%.
    coe = 0.09
    pv = 0.0
    dividend = dps_2025
    for year in range(1, 11):
        dividend *= 1.0 + g1
        pv += dividend / (1.0 + coe) ** year
    pv += (dividend * 1.025 / (coe - 0.025)) / (1.0 + coe) ** 10
    assert result.intrinsic_value_per_share == pytest.approx(pv)
    assert result.sensitivity == {}
