"""Unit tests for the shared WACC computation and the Yahoo provider fix.

Hermetic: the provider's network getters are replaced by fixtures, and the
DCF path uses a stub price service. No yfinance, no database.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.providers.yahoo.provider import YahooFinanceProvider
from backend.valuation.dcf import DCFValuation
from backend.valuation.wacc import compute_wacc


class _StubProvider(YahooFinanceProvider):
    """Provider whose data getters return fixed values instead of network."""

    def __init__(self, *, beta, market_cap, interest, debt, equity):
        self._fixture = SimpleNamespace(
            beta=beta,
            market_cap=market_cap,
            interest=interest,
            debt=debt,
            equity=equity,
        )

    def get_beta(self, ticker):
        return self._fixture.beta

    def get_market_cap(self, ticker):
        return self._fixture.market_cap

    def get_income_statement(self, ticker, year_index=0):
        return SimpleNamespace(interest_expense=self._fixture.interest)

    def get_balance_sheet(self, ticker, year_index=0):
        return SimpleNamespace(
            total_debt=self._fixture.debt,
            stockholders_equity=self._fixture.equity,
        )


class _Prices:
    def __init__(self, beta, market_cap):
        self._beta = beta
        self._market_cap = market_cap

    def get_beta(self, ticker):
        return self._beta

    def get_market_cap(self, ticker):
        return self._market_cap


def _row(**overrides):
    base = {
        "ticker": "T",
        "fiscal_year": 2024,
        "period": "FY",
        "interest_expense": 5_000_000_000.0,
        "total_debt": 100_000_000_000.0,
        "stockholders_equity": 50_000_000_000.0,
    }
    base.update(overrides)
    return NormalizedFinancials(**base)


def test_compute_wacc_known_inputs():
    # beta 1.2 -> CoE 10%; CoD 5%; E 200B / D 100B.
    wacc = compute_wacc(
        beta=1.2,
        interest_expense=5e9,
        total_debt=100e9,
        market_cap=200e9,
    )
    expected = (2 / 3) * 0.10 + (1 / 3) * 0.05 * (1 - 0.21)
    assert wacc == pytest.approx(expected)


def test_provider_returns_real_wacc_not_hardcoded():
    provider = _StubProvider(
        beta=1.2, market_cap=200e9, interest=5e9, debt=100e9, equity=50e9
    )
    wacc = provider.get_wacc("T")
    assert wacc == pytest.approx((2 / 3) * 0.10 + (1 / 3) * 0.05 * (1 - 0.21))
    assert wacc != pytest.approx(0.08)


def test_provider_matches_dcf_for_same_fixture():
    prices = _Prices(beta=1.2, market_cap=200e9)
    dcf_wacc = DCFValuation()._wacc(_row(), prices, "T", None)
    provider = _StubProvider(
        beta=1.2, market_cap=200e9, interest=5e9, debt=100e9, equity=50e9
    )
    assert provider.get_wacc("T") == pytest.approx(dcf_wacc)


def test_provider_beta_missing_defaults_to_one():
    provider = _StubProvider(
        beta=None, market_cap=200e9, interest=5e9, debt=100e9, equity=50e9
    )
    wacc = provider.get_wacc("T")
    expected = (2 / 3) * 0.09 + (1 / 3) * 0.05 * (1 - 0.21)
    assert wacc == pytest.approx(expected)


def test_provider_missing_interest_uses_cost_of_equity():
    provider = _StubProvider(
        beta=1.0, market_cap=100e9, interest=None, debt=50e9, equity=None
    )
    wacc = provider.get_wacc("T")
    # CoD falls back to CoE (9%); weights E 100 / D 50.
    expected = (2 / 3) * 0.09 + (1 / 3) * 0.09 * (1 - 0.21)
    assert wacc == pytest.approx(expected)


def test_provider_missing_debt_returns_cost_of_equity():
    provider = _StubProvider(
        beta=1.0, market_cap=100e9, interest=None, debt=None, equity=None
    )
    assert provider.get_wacc("T") == pytest.approx(0.09)


def test_provider_book_equity_fallback_without_market_cap():
    provider = _StubProvider(
        beta=1.0, market_cap=None, interest=5e9, debt=50e9, equity=100e9
    )
    # Book equity 100B; CoE 9%; CoD 10%; weights E 100 / D 50.
    expected = (2 / 3) * 0.09 + (1 / 3) * 0.10 * (1 - 0.21)
    assert provider.get_wacc("T") == pytest.approx(expected)


def test_provider_without_any_equity_returns_cost_of_equity():
    provider = _StubProvider(
        beta=1.0, market_cap=None, interest=5e9, debt=50e9, equity=None
    )
    assert provider.get_wacc("T") == pytest.approx(0.09)
