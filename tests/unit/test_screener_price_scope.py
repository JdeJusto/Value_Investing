"""
Regression tests for the "prices only for the queried tickers" guarantee.

The screener fetches real-time prices via PriceService strictly for the
tickers in the current query (--tickers / --search / universe file) and never
for the whole static universe. Prices are never persisted.

Covered here:
- prices fetched only for the requested tickers
- --no-prices never touches PriceService (and stays offline)
- PE / EV-EBIT valuation filters drive the market screener
- the investment (Buffett) screener enriches with real-time prices
  only for the tickers it is asked to screen
"""

from unittest.mock import Mock

import pytest

from backend.domain.value_objects.filter_criteria import FilterCriteria
from backend.services.screener_service import StockScreenerService


class _RecordingPriceService:
    """PriceService double that records every ticker it is asked for."""

    def __init__(self, price=200.0, shares=5_000_000_000):
        self.price = price
        self.shares = shares
        self.fetched: list[str] = []

    def get_current_price(self, ticker: str):
        self.fetched.append(ticker)
        return self.price

    def get_shares_outstanding(self, ticker: str):
        return self.shares


def _analysis(ticker, **overrides):
    base = {
        "ticker": ticker,
        "market_cap": None,
        "revenue": 100_000_000_000,
        "net_income": 10_000_000_000,
        "ebit": 12_000_000_000,
        "fcf": 8_000_000_000,
        "total_debt": 6_000_000_000,
        "equity": 20_000_000_000,
        "cash_and_equivalents": 2_000_000_000,
        "per": None,
        "pb": None,
        "fcf_yield": None,
        "ev_ebit": None,
        "roe": 0.2,
        "roic": 0.15,
        "operating_margin": 0.3,
        "net_margin": 0.1,
        "debt_to_equity": 0.4,
        "revenue_growth": 0.08,
        "score": 0.7,
    }
    base.update(overrides)
    return base


def _market_service(price_service):
    repo = Mock()
    market = Mock()
    market.get_company_name.return_value = "Test Company"
    service = StockScreenerService(
        repository=repo,
        market_provider=market,
        price_service=price_service,
    )
    service._analysis = Mock()
    return service


class TestMarketScreenerPriceScope:
    def test_prices_fetched_only_for_requested_tickers(self):
        """PriceService is called only for the tickers in the screen query."""
        prices = _RecordingPriceService()
        s = _market_service(prices)
        s._analysis.analyze.side_effect = [
            _analysis("AAPL"),
            _analysis("MSFT"),
            _analysis("KO"),
        ]

        results = s.screen(tickers=["AAPL", "MSFT", "KO"], filters=[], top_n=None)

        assert [r.ticker for r in results] == ["AAPL", "MSFT", "KO"]
        assert sorted(prices.fetched) == ["AAPL", "KO", "MSFT"]
        assert "NVDA" not in prices.fetched  # never touches the whole universe

    def test_price_fetched_once_per_ticker(self):
        """screen() fetches each queried ticker exactly once."""
        prices = _RecordingPriceService()
        s = _market_service(prices)
        s._analysis.analyze.side_effect = [
            _analysis("AAPL"),
            _analysis("MSFT"),
        ]

        s.screen(tickers=["AAPL", "MSFT"], filters=[], top_n=None)

        assert prices.fetched.count("AAPL") == 1
        assert prices.fetched.count("MSFT") == 1

    def test_no_prices_skips_price_service_entirely(self):
        """--no-prices mode never calls PriceService."""
        prices = Mock()
        prices.get_current_price.side_effect = AssertionError("must not be called")
        s = _market_service(prices)
        s._analysis.analyze.side_effect = [
            _analysis("AAPL"),
            _analysis("MSFT"),
        ]

        results = s.screen(tickers=["AAPL", "MSFT"], no_prices=True, top_n=None)

        assert len(results) == 2
        for row in results:
            assert row.price is None
            assert row.per is None
            assert row.ev_ebit is None

    def test_no_prices_rows_keep_fundamentals(self):
        """Even without prices, fundamentals are still returned."""
        prices = Mock()
        s = _market_service(prices)
        s._analysis.analyze.return_value = _analysis("KO")

        row = s.screen(tickers=["KO"], no_prices=True, top_n=None)[0]

        assert row.operating_margin == 0.3
        assert row.roe == 0.2
        assert row.debt_to_equity == 0.4

    def test_ev_ebit_filter_selects_cheapest_quarters(self):
        """EV/EBIT is computed from real-time price and used as a filter."""
        prices = _RecordingPriceService()
        s = _market_service(prices)
        # Low EV/EBIT company vs a rich one.
        s._analysis.analyze.side_effect = [
            _analysis("AAPL", ebit=2_000_000_000_000),  # EV/EBIT ~ 0.5
            _analysis("MSFT", ebit=100_000_000),        # EV/EBIT ~ 10k
        ]

        filters = [FilterCriteria.lt("ev_ebit", 20)]
        results = s.screen(tickers=["AAPL", "MSFT"], filters=filters, top_n=None)

        assert [r.ticker for r in results] == ["AAPL"]
        assert results[0].ev_ebit < 20

    def test_pe_filter_selects_cheap_stocks(self):
        """P/E from real-time price feeds the --pe-max filter."""
        prices = _RecordingPriceService()
        s = _market_service(prices)
        s._analysis.analyze.side_effect = [
            _analysis("AAPL", net_income=500_000_000_000),  # P/E ~ 2
            _analysis("MSFT", net_income=2_000_000_000),    # P/E ~ 500
        ]

        filters = [FilterCriteria.lt("per", 15)]
        results = s.screen(tickers=["AAPL", "MSFT"], filters=filters, top_n=None)

        assert [r.ticker for r in results] == ["AAPL"]


class TestInvestmentScreenerPriceScope:
    def test_investment_screener_fetches_prices_only_for_queried(self):
        """Buffett screener enriches with prices only for its universe."""
        from backend.screener.screener_service import ScreenerService

        prices = _RecordingPriceService(price=180.0, shares=4_000_000_000)
        by_ticker = {
            "BRK-B": _analysis("BRK-B", net_income=30_000_000_000),
            "XOM": _analysis("XOM", net_income=40_000_000_000),
        }
        analyzer = lambda ticker: dict(by_ticker[ticker])  # noqa: E731
        service = ScreenerService(
            analyzer=analyzer,
            universe=["BRK-B", "XOM"],
            price_service=prices,
        )

        results = service.run()

        assert sorted(prices.fetched) == ["BRK-B", "XOM"]
        assert len(results) == 2
        for r in results:
            assert r.metrics["price"] == 180.0
            assert r.metrics["per"] is not None
            assert r.metrics["market_cap"] == 180.0 * 4_000_000_000

    def test_investment_screener_no_prices_skips_service(self):
        """Buffett screener with no_prices never calls PriceService."""
        from backend.screener.screener_service import ScreenerService

        prices = Mock()
        prices.get_current_price.side_effect = AssertionError("must not be called")
        analyzer = lambda ticker: _analysis(ticker)  # noqa: E731
        service = ScreenerService(
            analyzer=analyzer,
            universe=["AAPL"],
            price_service=prices,
            no_prices=True,
        )

        results = service.run()

        assert len(results) == 1
        assert results[0].metrics is None

    def test_price_failure_keeps_company_in_screen(self):
        """A price-service failure leaves the company visible, metrics empty."""
        from backend.screener.screener_service import ScreenerService

        prices = Mock()
        prices.get_current_price.side_effect = Exception("rate limited")
        analyzer = lambda ticker: _analysis(ticker, score=0.95)  # noqa: E731
        service = ScreenerService(
            analyzer=analyzer,
            universe=["KO"],
            price_service=prices,
        )

        results = service.run()

        assert len(results) == 1
        assert results[0].metrics == {}


if __name__ == "__main__":
    pytest.main([__file__])