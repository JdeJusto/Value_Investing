"""Hermetic tests for the DCF company-type variants (REIT / DDM / hyper-growth).

``evaluate`` dispatches on the shared company-type detector; these tests pin
the dispatch decisions, the variant labels on ``DCFResult``, and the honest
INSUFFICIENT_DATA paths (nothing is fabricated from missing cash flows).
No network, no database, no prices persisted.
"""

from __future__ import annotations

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.valuation.base import DCFAssumptions
from backend.valuation.dcf import INSUFFICIENT_DATA, DCFValuation


class _Prices:
    """Read-only stub that fails loudly if a variant reaches beyond 3 reads."""

    def __init__(self, price=20.0, market_cap=30_000_000_000.0, beta=1.0):
        self._price = price
        self._market_cap = market_cap
        self._beta = beta
        self.calls = []

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


def _evaluate(rows, *, price=20.0, market_cap=30_000_000_000.0, beta=1.0):
    stub = _Prices(price=price, market_cap=market_cap, beta=beta)
    result = DCFValuation().evaluate("TEST", rows, stub)
    return result, stub


# ---------------------------------------------------------------------------
# REIT — funds from operations
# ---------------------------------------------------------------------------
def _reit_rows(ffo_years, shares=1_200_000_000, sector="Real Estate"):
    rows = []
    for i, ffo in enumerate(ffo_years):
        year = 2025 - i
        net_income = ffo * 0.6
        rows.append(
            _row(
                year,
                revenue=8_000_000_000,
                net_income=net_income,
                depreciation_amortization=ffo - net_income,
                operating_cash_flow=-1_000_000_000,  # FCF would be negative
                capital_expenditure=2_000_000_000,
                shares_outstanding=shares,
                sector=sector,
            )
        )
    return rows


def test_reit_dispatch_and_ffo_base():
    rows = _reit_rows([3_500_000_000, 3_200_000_000, 3_000_000_000])
    result, _ = _evaluate(rows, price=15.0)
    assert result.variant == "reit"
    assert result.verdict != INSUFFICIENT_DATA
    # FFO base = mean of the three FFOs, unaffected by the negative FCF.
    expected_base = (3_500_000_000 + 3_200_000_000 + 3_000_000_000) / 3
    assert result.fcf_base == expected_base
    assert result.fcf_years == 3
    assert result.intrinsic_value_per_share is not None
    joined = " ".join(result.reasons)
    assert "funds from operations" in joined
    assert "real estate" in joined


def test_reit_keyword_and_utilities_keyword_only_match_own_tiers():
    # "Real Estate Investment Trusts" and bare "REIT" both resolve.
    rows = _reit_rows([3_500_000_000], sector="Real Estate Investment Trusts")
    result, _ = _evaluate(rows)
    assert result.variant == "reit"
    rows = _reit_rows([3_500_000_000], sector="REIT")
    result, _ = _evaluate(rows)
    assert result.variant == "reit"


def test_reit_insufficient_without_ffo_components():
    rows = [_row(2025, revenue=8e9, shares_outstanding=1.2e9, sector="Real Estate")]
    result, _ = _evaluate(rows)
    assert result.verdict == INSUFFICIENT_DATA
    assert result.variant == "reit"
    assert result.missing_inputs == ["funds from operations"]


def test_reit_insufficient_with_negative_ffo():
    rows = _reit_rows([-1_000_000_000])
    result, _ = _evaluate(rows)
    assert result.verdict == INSUFFICIENT_DATA
    assert result.missing_inputs == ["positive funds from operations"]


# ---------------------------------------------------------------------------
# Financial — two-stage dividend discount model (sector hint route)
# ---------------------------------------------------------------------------
def test_financial_sector_hint_routes_to_two_stage_ddm():
    rows = [
        _row(
            2025,
            revenue=182e9,
            net_income=55.7e9,
            operating_cash_flow=85e9,
            capital_expenditure=1e9,
            shares_outstanding=2.78e9,
            dividends_paid=12e9,
            sector="Financial Services",
        ),
        _row(
            2024,
            revenue=167e9,
            net_income=50e9,
            operating_cash_flow=80e9,
            capital_expenditure=1e9,
            shares_outstanding=2.9e9,
            dividends_paid=11.6e9,
            sector="Financial Services",
        ),
        _row(
            2023,
            revenue=155e9,
            net_income=48e9,
            operating_cash_flow=75e9,
            capital_expenditure=1e9,
            shares_outstanding=2.95e9,
            dividends_paid=11.2e9,
            sector="Financial Services",
        ),
    ]
    result, _ = _evaluate(rows, beta=1.0)
    assert result.variant == "ddm_financial_two_stage"
    assert result.verdict != INSUFFICIENT_DATA
    # dps 2025 = 12e9/2.78e9; dps 2023 = 11.2e9/2.95e9; CAGR over 2 years.
    dps_2025 = 12e9 / 2.78e9
    dps_2023 = 11.2e9 / 2.95e9
    g1 = (dps_2025 / dps_2023) ** 0.5 - 1.0
    assert result.growth_1_5 == pytest.approx(g1)
    assert result.wacc == 0.09
    coe = 0.09
    pv = 0.0
    dividend = dps_2025
    for year in range(1, 11):
        dividend *= 1.0 + g1
        pv += dividend / (1.0 + coe) ** year
    pv += (dividend * 1.025 / (coe - 0.025)) / (1.0 + coe) ** 10
    assert result.intrinsic_value_per_share == pytest.approx(pv)


def test_financial_sector_hint_without_dividends_insufficient():
    rows = [
        _row(
            2025,
            revenue=182e9,
            net_income=55.7e9,
            shares_outstanding=2.78e9,
            sector="Banks—Diversified",
        )
    ]
    result, _ = _evaluate(rows)
    assert result.verdict == INSUFFICIENT_DATA
    assert result.variant == "ddm_financial"
    assert result.missing_inputs == ["dividends per share"]
    joined = " ".join(result.reasons)
    assert "Financial company" in joined
    assert "banks/insurers" in joined


# ---------------------------------------------------------------------------
# Two-stage DDM — high-growth banks (the JPM/WFC failure mode)
# ---------------------------------------------------------------------------
def _bank_rows(dps_years, shares=2_000_000_000, sector="Financial Services"):
    """Newest-first bank rows producing the given DPS sequence."""
    rows = []
    for i, dps in enumerate(dps_years):
        year = 2025 - i
        rows.append(
            _row(
                year,
                revenue=100e9,
                net_income=30e9,
                shares_outstanding=shares,
                dividends_paid=dps * shares,
                sector=sector,
            )
        )
    return rows


def test_two_stage_ddm_high_growth_produces_sane_value():
    # DPS 1.00 -> 1.20 -> 1.44 is a 20% CAGR, capped at the documented 12%.
    rows = _bank_rows([1.44, 1.20, 1.00])
    result, _ = _evaluate(rows, beta=1.0)
    assert result.variant == "ddm_financial_two_stage"
    assert result.growth_1_5 == pytest.approx(0.12)
    assert result.verdict != INSUFFICIENT_DATA
    coe = 0.09
    pv = 0.0
    dividend = 1.44
    for year in range(1, 11):
        dividend *= 1.12
        pv += dividend / (1.0 + coe) ** year
    pv += (dividend * 1.025 / (coe - 0.025)) / (1.0 + coe) ** 10
    assert result.intrinsic_value_per_share == pytest.approx(pv)
    joined = " ".join(result.reasons)
    assert "two-stage" in joined


def test_two_stage_ddm_low_growth_falls_back_to_single_stage():
    # 1% DPS CAGR is below the 2.5% terminal rate: no high-growth stage to
    # model, so the single-stage Gordon model is used.
    rows = _bank_rows([1.0201, 1.01, 1.00])
    result, _ = _evaluate(rows, beta=1.0)
    assert result.variant == "ddm_financial"
    assert result.growth_1_5 == pytest.approx(0.01)
    expected = 1.0201 * 1.01 / (0.09 - 0.01)
    assert result.intrinsic_value_per_share == pytest.approx(expected)
    joined = " ".join(result.reasons)
    assert "Single-stage chosen" in joined


def test_two_stage_ddm_cagr_not_computable_falls_back():
    # 2023 paid zero dividends: no CAGR, but D_0 exists, so the fallback
    # uses the mean year-over-year growth of the valid pairs (5.26%).
    rows = _bank_rows([1.00, 0.95, 0.0])
    result, _ = _evaluate(rows, beta=1.0)
    assert result.variant == "ddm_financial"
    g = 1.00 / 0.95 - 1.0
    assert result.growth_1_5 == pytest.approx(g)
    expected = 1.00 * (1.0 + g) / (0.09 - g)
    assert result.intrinsic_value_per_share == pytest.approx(expected)


def test_two_stage_ddm_insufficient_history_insufficient():
    # Two dividend years cannot produce a CAGR; the model refuses to guess.
    rows = _bank_rows([1.10, 1.00])
    result, _ = _evaluate(rows, beta=1.0)
    assert result.verdict == INSUFFICIENT_DATA
    assert result.missing_inputs == ["dividend history (>= 3 years)"]
    joined = " ".join(result.reasons)
    assert "3 required" in joined


def test_two_stage_ddm_terminal_growth_ge_cost_of_equity_insufficient():
    # terminal growth 10% >= cost of equity 9%: the terminal denominator is
    # undefined, so the model reads INSUFFICIENT_DATA.
    rows = _bank_rows([1.44, 1.20, 1.00])
    stub = _Prices(price=20.0, market_cap=30_000_000_000.0, beta=1.0)
    valuation = DCFValuation(DCFAssumptions(terminal_growth=0.10))
    result = valuation.evaluate("TEST", rows, stub)
    assert result.verdict == INSUFFICIENT_DATA
    assert result.missing_inputs == ["cost of equity > terminal growth"]
    assert result.intrinsic_value_per_share is None


def test_two_stage_ddm_deterministic_across_runs():
    rows = _bank_rows([1.44, 1.20, 1.00])
    first, _ = _evaluate(rows, beta=1.0)
    second, _ = _evaluate(rows, beta=1.0)
    assert first.variant == second.variant
    assert first.intrinsic_value_per_share == second.intrinsic_value_per_share
    assert first.verdict == second.verdict


# ---------------------------------------------------------------------------
# DDM preferred dividend adjustment
# ---------------------------------------------------------------------------
def _bank_rows_with_preferred(dps_years, preferred_per_share=0.2, shares=2_000_000_000):
    """Bank rows whose total dividend includes a tagged preferred slice."""
    rows = []
    for i, dps in enumerate(dps_years):
        year = 2025 - i
        rows.append(
            _row(
                year,
                revenue=100e9,
                net_income=30e9,
                shares_outstanding=shares,
                dividends_paid=(dps + preferred_per_share) * shares,
                preferred_dividends=preferred_per_share * shares,
                sector="Financial Services",
            )
        )
    return rows


def test_ddm_subtracts_preferred_dividends():
    # Same total paid in both cases; only the second tags the preferred slice,
    # so its common base (and value) must be lower.
    baseline, _ = _evaluate(_bank_rows([1.64, 1.40, 1.20]), beta=1.0)
    adjusted, _ = _evaluate(_bank_rows_with_preferred([1.44, 1.20, 1.00]), beta=1.0)
    assert baseline.preferred_dividend_adjusted is False
    assert adjusted.preferred_dividend_adjusted is True
    assert adjusted.intrinsic_value_per_share < baseline.intrinsic_value_per_share
    assert any("Preferred dividends" in r for r in adjusted.reasons)


def test_ddm_preferred_adjustment_recovers_common_dividend():
    # A tagged preferred slice on top of the common dividend must land on the
    # same value as filing only the common dividend.
    plain, _ = _evaluate(_bank_rows([1.44, 1.20, 1.00]), beta=1.0)
    tagged, _ = _evaluate(_bank_rows_with_preferred([1.44, 1.20, 1.00]), beta=1.0)
    assert tagged.preferred_dividend_adjusted is True
    assert tagged.intrinsic_value_per_share == pytest.approx(
        plain.intrinsic_value_per_share
    )


def test_preferred_adjustment_not_applied_to_non_financials():
    rows = _standard_rows([6e9, 5e9, 4e9])
    for row in rows:
        row.preferred_dividends = 1e9
    result, _ = _evaluate(rows, price=10.0)
    assert result.variant == "standard"
    assert result.preferred_dividend_adjusted is False


def test_ddm_preferred_exceeding_total_is_insufficient():
    # Preferred cannot exceed the total paid: the DDM must not floor it
    # silently to zero.
    rows = [
        _row(
            2025,
            revenue=100e9,
            net_income=30e9,
            shares_outstanding=2_000_000_000,
            dividends_paid=1_000_000_000,
            preferred_dividends=2_000_000_000,
            sector="Financial Services",
        ),
        _row(
            2024,
            revenue=95e9,
            net_income=28e9,
            shares_outstanding=2_000_000_000,
            dividends_paid=900_000_000,
            preferred_dividends=800_000_000,
            sector="Financial Services",
        ),
        _row(
            2023,
            revenue=90e9,
            net_income=26e9,
            shares_outstanding=2_000_000_000,
            dividends_paid=850_000_000,
            preferred_dividends=750_000_000,
            sector="Financial Services",
        ),
    ]
    result, _ = _evaluate(rows, beta=1.0)
    assert result.verdict == INSUFFICIENT_DATA
    assert result.missing_inputs == ["consistent dividend data"]
    joined = " ".join(result.reasons)
    assert "exceed total dividends" in joined
    assert "check source data" in joined


def test_ddm_preferred_adjustment_documents_growth_effect():
    adjusted, _ = _evaluate(_bank_rows_with_preferred([1.44, 1.20, 1.00]), beta=1.0)
    assert any(
        "true common-dividend trajectory" in reason for reason in adjusted.reasons
    )


def test_ddm_without_adjustment_has_no_preferred_reason():
    baseline, _ = _evaluate(_bank_rows([1.64, 1.40, 1.20]), beta=1.0)
    assert not any("Preferred dividends" in reason for reason in baseline.reasons)
    assert baseline.preferred_dividend_adjusted is False


# ---------------------------------------------------------------------------
# Hyper-growth — observed positive FCF years only
# ---------------------------------------------------------------------------
def _hyper_rows(fcf_window, revenue_2025=260e9, sector=None):
    """Newest-first rows with >25% revenue CAGR over 2021-2025."""
    rows = []
    for i, fcf in enumerate(fcf_window):
        year = 2025 - i
        # 2021 -> 100e9, 2022 -> 116e9, ... grows 26.7% annually to 260e9.
        rev = 100e9 * (1.2667 ** (year - 2021))
        rows.append(
            _row(
                year,
                revenue=rev,
                net_income=3e9,
                operating_cash_flow=5e9,
                capital_expenditure=5e9 - fcf,
                free_cash_flow=fcf,
                shares_outstanding=1_000_000_000,
                inventory=5e9,
                sector=sector,
            )
        )
    return rows


def test_hyper_growth_dispatch_and_positive_base():
    # Latest FCF negative (classifies hyper-growth) but two older window years
    # were cash-positive: the base uses only the observed positives.
    rows = _hyper_rows([-4e9, 2e9, 4e9])
    result, _ = _evaluate(rows, price=10.0)
    assert result.variant == "hyper_growth"
    assert result.verdict != INSUFFICIENT_DATA
    assert result.fcf_base == 3e9
    assert result.fcf_years == 2
    joined = " ".join(result.reasons)
    assert "Hyper-growth" in joined


def test_hyper_growth_still_cash_burning_insufficient():
    rows = _hyper_rows([-4e9, -2e9, -6e9])
    result, _ = _evaluate(rows)
    assert result.verdict == INSUFFICIENT_DATA
    assert result.variant == "hyper_growth"
    assert result.missing_inputs == ["positive free cash flow"]


# ---------------------------------------------------------------------------
# Everything else stays on the standard free-cash-flow DCF
# ---------------------------------------------------------------------------
def _standard_rows(fcf, shares=1_000_000_000, sector=None):
    rows = []
    for i, v in enumerate(fcf):
        year = 2025 - i
        rows.append(
            _row(
                year,
                revenue=40e9,
                net_income=5e9,
                operating_cash_flow=v + 3e9,
                capital_expenditure=3e9,
                free_cash_flow=v,
                shares_outstanding=shares,
                inventory=5e9,
                sector=sector,
            )
        )
    return rows


def test_utility_keeps_standard_dcf():
    rows = _standard_rows([6e9, 5e9, 4e9], sector="Utilities")
    result, _ = _evaluate(rows, price=10.0)
    assert result.variant == "standard"
    assert result.verdict != INSUFFICIENT_DATA
    assert result.fcf_base == 5e9


def test_unknown_sector_keeps_standard_dcf():
    rows = _standard_rows([6e9, 5e9, 4e9])
    result, _ = _evaluate(rows, price=10.0)
    assert result.variant == "standard"
    assert result.verdict != INSUFFICIENT_DATA


def test_standard_sensitivity_grid_only_for_multiyear_variants():
    # The standard variant keeps its 3x3 grid; the DDM has none.
    rows = _standard_rows([6e9, 5e9, 4e9])
    result, _ = _evaluate(rows, price=10.0)
    assert result.sensitivity  # non-empty
    ddm, _ = _evaluate(_bank_rows([1.44, 1.20, 1.00]), beta=1.0)
    assert ddm.variant == "ddm_financial_two_stage"
    assert ddm.sensitivity == {}
