"""DCF INSUFFICIENT_DATA reasons (hermetic): one visible cause per variant."""

from __future__ import annotations

from dataclasses import asdict

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.services.ui_adapter import build_dcf_view
from backend.valuation.base import DCFAssumptions
from backend.valuation.dcf import INSUFFICIENT_DATA, DCFValuation


class _Prices:
    def get_current_price(self, ticker):
        return 20.0

    def get_market_cap(self, ticker):
        return 30_000_000_000.0

    def get_beta(self, ticker):
        return 1.0


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


def _evaluate(rows, assumptions=None):
    return DCFValuation(assumptions).evaluate("TEST", rows, _Prices())


def _standard_rows(fcf, shares=1_000_000_000):
    return [
        _row(
            2025 - index,
            revenue=40e9,
            net_income=5e9,
            operating_cash_flow=value + 3e9,
            capital_expenditure=3e9,
            free_cash_flow=value,
            shares_outstanding=shares,
            inventory=5e9,
        )
        for index, value in enumerate(fcf)
    ]


def test_negative_fcf_reason():
    result = _evaluate(_standard_rows([-1e9, -2e9, -3e9]))
    assert result.verdict == INSUFFICIENT_DATA
    assert result.reason == "FCF negative (last 3 years)"


def test_missing_fcf_history_reason():
    rows = [_row(2025, revenue=40e9, net_income=5e9, shares_outstanding=1e9)]
    result = _evaluate(rows)
    assert result.verdict == INSUFFICIENT_DATA
    assert result.reason == "Insufficient FCF history (need >=3 years)"


def test_missing_terminal_input_reason():
    # WACC (4% override) <= terminal growth (2.5%) is not the trigger; use a
    # 1% override so the terminal value is undefined.
    result = _evaluate(
        _standard_rows([6e9, 5e9, 4e9]),
        DCFAssumptions(wacc_override=0.01),
    )
    assert result.verdict == INSUFFICIENT_DATA
    assert result.reason == "Missing terminal value input (WACC or growth)"


def test_bank_without_dividends_reason():
    rows = [
        _row(
            2025,
            revenue=182e9,
            net_income=55.7e9,
            shares_outstanding=2.78e9,
            sector="Financial Services",
        )
    ]
    result = _evaluate(rows)
    assert result.variant == "ddm_financial"
    assert result.reason == (
        "Bank/insurer — DCF not applicable (no dividend stream for the DDM)"
    )


def test_short_dividend_history_reason():
    rows = [
        _row(
            2025 - index,
            revenue=182e9,
            net_income=50e9,
            shares_outstanding=2.78e9,
            dividends_paid=dividend * 2.78e9,
            sector="Financial Services",
        )
        for index, dividend in enumerate([1.10, 1.00])
    ]
    result = _evaluate(rows)
    assert result.verdict == INSUFFICIENT_DATA
    assert result.reason == "Insufficient dividend history for the DDM (need >=3 years)"


def test_reit_without_ffo_reason():
    rows = [_row(2025, revenue=8e9, shares_outstanding=1.2e9, sector="Real Estate")]
    result = _evaluate(rows)
    assert result.variant == "reit"
    assert result.reason == (
        "REIT — FFO not computable (net income or depreciation missing)"
    )


def test_json_payload_includes_the_reason_key():
    result = _evaluate(_standard_rows([-1e9, -2e9, -3e9]))
    payload = asdict(result)
    assert "reason" in payload
    assert payload["reason"] == "FCF negative (last 3 years)"


def test_ui_view_carries_the_reason():
    result = _evaluate(_standard_rows([-1e9, -2e9, -3e9]))
    view = build_dcf_view(result)
    assert view.is_insufficient is True
    assert view.reason == "FCF negative (last 3 years)"
