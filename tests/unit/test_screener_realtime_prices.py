"""
Unit tests for StockScreenerService real-time price integration.

Prices come from PriceService (never persisted) and are used to compute
valuation metrics (P/E, FCF yield, EV/EBIT) when the market provider fails.
"""

from unittest.mock import Mock

import pytest

from backend.domain.value_objects.screener_result import ScreenerRow
from backend.services.screener_service import StockScreenerService


class TestStockScreenerRealtimePrices:
    """Test the screener's real-time price handling."""

    @pytest.fixture
    def analysis_result(self):
        """A typical analyze() output without price-derived metrics."""
        return {
            "ticker": "AAPL",
            "market_cap": None,
            "revenue": 400_000_000_000,
            "net_income": 100_000_000_000,
            "ebit": 120_000_000_000,
            "fcf": 90_000_000_000,
            "total_debt": 100_000_000_000,
            "equity": 60_000_000_000,
            "cash_and_equivalents": 30_000_000_000,
            "per": None,
            "pb": None,
            "roe": 0.2,
            "roic": 0.17,
            "operating_margin": 0.3,
            "net_margin": 0.25,
            "fcf_yield": None,
            "ev_ebit": None,
            "debt_to_equity": 0.5,
            "revenue_growth": 0.05,
            "score": 0.8,
        }

    def _service(self, price, shares=None):
        repo = Mock()
        market = Mock()
        market.get_company_name.return_value = "Apple Inc."
        prices = Mock()
        prices.get_current_price.return_value = price
        prices.get_shares_outstanding.return_value = shares
        return StockScreenerService(
            repository=repo,
            market_provider=market,
            price_service=prices,
        )

    def test_enrich_computes_pe_and_fcf_yield(self, analysis_result):
        """Missing P/E and FCF yield are computed from real-time price."""
        service = self._service(price=200.0, shares=5_000_000_000)
        d = service._enrich_with_real_time_price(analysis_result, "AAPL", 200.0)

        market_cap = 200.0 * 5_000_000_000
        assert d["market_cap"] == market_cap
        assert d["per"] == pytest.approx(market_cap / 100_000_000_000)
        assert d["fcf_yield"] == pytest.approx(90_000_000_000 / market_cap)

    def test_enrich_computes_ev_ebit(self, analysis_result):
        """Missing EV/EBIT is computed when ebit and debt/cash are known."""
        service = self._service(price=200.0, shares=5_000_000_000)
        d = service._enrich_with_real_time_price(analysis_result, "AAPL", 200.0)

        market_cap = 200.0 * 5_000_000_000
        expected_ev = market_cap + 100_000_000_000 - 30_000_000_000
        assert d["ev_ebit"] == pytest.approx(expected_ev / 120_000_000_000)

    def test_enrich_no_price_keeps_original(self, analysis_result):
        """Without a price, the original metrics are preserved (graceful)."""
        service = self._service(price=None)
        d = service._enrich_with_real_time_price(analysis_result, "AAPL", None)

        assert d["per"] is None
        assert d["fcf_yield"] is None
        assert d["market_cap"] is None

    def test_enrich_no_shares_keeps_original(self, analysis_result):
        """Without shares outstanding, price-dependent metrics are skipped."""
        service = self._service(price=200.0, shares=None)
        d = service._enrich_with_real_time_price(analysis_result, "AAPL", 200.0)

        assert d["per"] is None
        assert d["fcf_yield"] is None

    def test_analyze_ticker_builds_row_with_realtime_price(self, analysis_result):
        """_analyze_ticker uses the real-time price in the ScreenerRow."""
        service = self._service(price=200.0, shares=5_000_000_000)
        service._analysis = Mock()
        service._analysis.analyze.return_value = dict(analysis_result)

        row = service._analyze_ticker("AAPL")

        assert isinstance(row, ScreenerRow)
        assert row.price == 200.0
        assert row.name == "Apple Inc."
        assert row.per is not None
        assert row.fcf_yield is not None
        assert row.ev_ebit is not None

    def test_analyze_ticker_graceful_on_price_failure(self, analysis_result):
        """A price-service failure yields a row with fundamentals only."""
        service = self._service(price=None)
        service._price_service.get_current_price.side_effect = Exception("rate limited")
        service._analysis = Mock()
        service._analysis.analyze.return_value = dict(analysis_result)

        row = service._analyze_ticker("AAPL")

        assert isinstance(row, ScreenerRow)
        assert row.price is None
        assert row.per is None  # price-dependent -> skipped
        assert row.operating_margin == 0.3  # fundamentals intact
        assert row.net_margin == 0.25

    def test_screen_skips_exceptions(self, analysis_result):
        """screen() continue past tickers that raise."""
        service = self._service(price=200.0, shares=5_000_000_000)
        service._analysis = Mock()
        service._analysis.analyze.side_effect = [
            dict(analysis_result),
            Exception("no data"),
        ]

        results = service.screen(tickers=["AAPL", "XDATA"], filters=[], top_n=None)

        assert len(results) == 1
        assert results[0].ticker == "AAPL"


if __name__ == "__main__":
    pytest.main([__file__])
