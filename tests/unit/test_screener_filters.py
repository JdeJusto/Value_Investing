"""Screener eligibility: funds/trusts/SPACs are excluded by default."""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.services.screener_filters import is_investable_company
from backend.services.ui_adapter import enrich_rows


def _row(ticker="X", year=2025, revenue=None, net_income=None):
    return NormalizedFinancials(
        ticker=ticker,
        fiscal_year=year,
        period="FY",
        revenue=revenue,
        net_income=net_income,
    )


def test_fund_without_data_is_excluded():
    history = [_row(2025), _row(2024), _row(2023)]
    assert not is_investable_company(
        history[0], history, name="Nuveen Core Equity Alpha Fund"
    )


def test_spac_without_data_is_excluded():
    history = [_row(2025), _row(2024), _row(2023)]
    assert not is_investable_company(
        history[0], history, name="Bluerock Acquisition Corp."
    )


def test_operating_company_with_revenue_is_included():
    history = [_row(2025, revenue=1_000.0), _row(2024, revenue=900.0)]
    assert is_investable_company(history[0], history, name="Apple Inc.")


def test_no_revenue_but_net_income_and_normal_name_is_included():
    # Some industrials report irregular revenue; a real bottom line keeps them.
    history = [_row(2025, net_income=50.0), _row(2024)]
    assert is_investable_company(history[0], history, name="Laramide Resources Ltd")


def test_no_revenue_with_fund_name_is_excluded_even_with_net_income():
    history = [_row(2025, net_income=12.0)]
    assert not is_investable_company(
        history[0], history, name="JOHN HANCOCK PREFERRED INCOME FUND II"
    )


def test_bank_named_trust_with_revenue_is_not_excluded_by_name():
    history = [_row(2025, revenue=5_000.0)]
    assert is_investable_company(history[0], history, name="Northern Trust Corp")


def test_missing_row_is_investable():
    assert is_investable_company(None, None, name="Whatever Fund")


def _loaders(rows_by_ticker, names):
    def load_fundamentals(ticker):
        return rows_by_ticker.get(ticker, [])

    from dataclasses import dataclass, field

    @dataclass
    class _View:
        details: list = field(
            default_factory=lambda: [
                {"methodology": "buffett_classic", "verdict": "BUY", "score": 80.0}
            ]
        )
        category: str | None = "Quality"

    def run_methodologies(ticker, fundamentals, price):
        return _View()

    return load_fundamentals, run_methodologies


def test_enrich_rows_excludes_funds_by_default_and_toggle_includes_them():
    rows_by_ticker = {
        "AAPL": [_row("AAPL", revenue=1_000.0)],
        "FUNDX": [_row("FUNDX")],
    }
    screener_rows = [
        {"ticker": "AAPL", "name": "Apple Inc."},
        {"ticker": "FUNDX", "name": "Some Income Fund"},
    ]
    load, run = _loaders(rows_by_ticker, {})
    default = enrich_rows(screener_rows, "buffett_classic", {}, load, run, workers=1)
    assert [r["Ticker"] for r in default] == ["AAPL"]
    with_funds = enrich_rows(
        screener_rows, "buffett_classic", {}, load, run, workers=1, include_funds=True
    )
    assert [r["Ticker"] for r in with_funds] == ["AAPL", "FUNDX"]
