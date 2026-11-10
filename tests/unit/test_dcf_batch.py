"""Batch price adapters expose ``get_beta`` so the DCF rule stays active.

Before v0.27.1 the batch adapters only implemented ``get_current_price`` and
``get_market_cap``; ``DCFValuation`` raised ``AttributeError`` on ``get_beta``
and the Buffett DCF rule silently degraded to ``N/A`` in rank, screener and
backtest. These tests pin the adapter surface and the resulting rule outcome.
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.buffett_classic.methodology import (
    BuffettClassicMethodology,
)
from backend.services.methodology_backtest_service import _HistoricalPrices
from backend.services.price_adapter import BatchPriceContext


def _row(year: int, **overrides):
    data = {
        "ticker": "TEST",
        "fiscal_year": year,
        "period": "FY",
        "currency": "USD",
        "source": "sec_edgar",
        "shares_outstanding": 100,
        "split_adjustment_factor": 1.0,
        "sector": "Industrials",
    }
    data.update(overrides)
    return NormalizedFinancials.from_dict(data)


def _dcf_friendly_rows():
    """Five years of positive FCF with enough inputs for the standard DCF."""
    rows = []
    for index in range(5):
        growth = 1.05 ** (4 - index)
        rows.append(
            _row(
                2025 - index,
                revenue=100 * growth,
                gross_profit=60 * growth,
                ebit=40 * growth,
                operating_income=40 * growth,
                net_income=25 * growth,
                free_cash_flow=21 * growth,
                operating_cash_flow=23 * growth,
                depreciation_amortization=5,
                capital_expenditure=2,
                total_debt=20,
                stockholders_equity=100,
                cash_and_equivalents=10,
                current_assets=200,
                current_liabilities=100,
                interest_expense=1,
                tax_provision=0,
                pretax_income=100,
                shares_outstanding=100 - (4 - index),
                repurchase_of_stock=1,
                research_development=5,
            )
        )
    return rows


def _dcf_reason(result) -> str:
    return next(reason for reason in result.reasons if "DCF" in reason)


# ---------------------------------------------------------------------------
# adapter surface
# ---------------------------------------------------------------------------
def test_batch_price_adapter_exposes_get_beta():
    context = BatchPriceContext(100.0, 1_000.0, 1.2)

    assert context.get_current_price("AAPL") == 100.0
    assert context.get_market_cap("AAPL") == 1_000.0
    assert context.get_beta("AAPL") == 1.2


def test_batch_price_adapter_allows_missing_beta():
    context = BatchPriceContext(100.0, 1_000.0)
    assert context.get_beta("AAPL") is None


def test_historical_prices_exposes_get_beta():
    context = _HistoricalPrices(100.0, 1_000.0)
    assert context.get_beta("AAPL") is None  # 1.0 fallback avoids look-ahead
    assert context.get_beta("AAPL") is None
    assert _HistoricalPrices(100.0, 1_000.0, 1.1).get_beta("AAPL") == 1.1


# ---------------------------------------------------------------------------
# the rule is evaluated, not N/A
# ---------------------------------------------------------------------------
def test_dcf_rule_computed_with_a_batch_adapter():
    result = BuffettClassicMethodology().evaluate(
        "TEST", _dcf_friendly_rows(), BatchPriceContext(4.0, 400.0, 1.2)
    )

    assert result.metrics.get("dcf_margin_of_safety") is not None
    assert result.metrics.get("dcf_intrinsic_value") is not None
    reason = _dcf_reason(result)
    assert "[N/A]" not in reason
    assert "[PASS]" in reason or "[FAIL]" in reason


def test_dcf_rule_computed_with_the_one_fallback_beta():
    result = BuffettClassicMethodology().evaluate(
        "TEST", _dcf_friendly_rows(), BatchPriceContext(4.0, 400.0)
    )

    assert result.metrics.get("dcf_margin_of_safety") is not None
    assert "[N/A]" not in _dcf_reason(result)


def test_dcf_rule_computed_in_the_backtest_context():
    result = BuffettClassicMethodology().evaluate(
        "TEST", _dcf_friendly_rows(), _HistoricalPrices(4.0, 400.0)
    )

    assert result.metrics.get("dcf_margin_of_safety") is not None
    assert "[N/A]" not in _dcf_reason(result)


def test_legacy_adapter_without_get_beta_still_degrades_to_na():
    """Regression guard: a context without get_beta is the old failure mode."""

    class _LegacyAdapter:
        def get_current_price(self, _ticker):
            return 4.0

        def get_market_cap(self, _ticker):
            return 400.0

    result = BuffettClassicMethodology().evaluate(
        "TEST", _dcf_friendly_rows(), _LegacyAdapter()
    )

    assert result.metrics.get("dcf_margin_of_safety") is None
    assert "[N/A]" in _dcf_reason(result)
