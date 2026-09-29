"""Hermetic tests for the DCF company-type variants (REIT / DDM / hyper-growth).

``evaluate`` dispatches on the shared company-type detector; these tests pin
the dispatch decisions, the variant labels on ``DCFResult``, and the honest
INSUFFICIENT_DATA paths (nothing is fabricated from missing cash flows).
No network, no database, no prices persisted.
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
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
# Financial — dividend discount model (sector hint route)
# ---------------------------------------------------------------------------
def test_financial_sector_hint_routes_to_ddm():
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
    ]
    result, _ = _evaluate(rows, beta=1.0)
    assert result.variant == "ddm_financial"
    assert result.verdict != INSUFFICIENT_DATA
    # dps 2025 = 12e9 / 2.78e9; dps 2024 = 11.6e9 / 2.9e9 = 4.0.
    dps = 12e9 / 2.78e9
    g = dps / 4.0 - 1.0
    assert result.growth_1_5 == g
    assert result.wacc == 0.09
    assert result.intrinsic_value_per_share == dps * (1 + g) / (0.09 - g)


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
    fin = _row(
        2025,
        revenue=80e9,
        net_income=12e9,
        shares_outstanding=2e9,
        dividends_paid=6e9,
        sector="Financial Services",
    )
    ddm, _ = _evaluate([fin], beta=1.0)
    assert ddm.sensitivity == {}
