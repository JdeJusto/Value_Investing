"""
Unit tests for PriceService (real-time price fetching without persistence).
"""

from datetime import date, datetime
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from backend.services.price_service import PriceService


def _make_history(dates, closes):
    """Build a yfinance-like history DataFrame."""
    return pd.DataFrame(
        {"Close": closes},
        index=pd.DatetimeIndex([datetime.combine(d, datetime.min.time()) for d in dates]),
    )


class TestPriceService:
    """Test PriceService class."""

    @pytest.fixture
    def service(self):
        """Create a PriceService with a short cache TTL."""
        return PriceService(cache_ttl=900)

    def test_get_current_price_success(self, service):
        """Test successful current price retrieval."""
        hist = _make_history([date(2024, 1, 2)], [150.25])
        mock_ticker = Mock()
        mock_ticker.history.return_value = hist

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            price = service.get_current_price("AAPL")

        assert price == 150.25
        mock_ticker.history.assert_called_once_with(period="1d")

    def test_get_current_price_empty_history(self, service):
        """Test current price when history is empty."""
        mock_ticker = Mock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            price = service.get_current_price("INVALID")

        assert price is None

    def test_get_current_price_retries_after_transient_empty(self, service):
        """A transient empty history window is retried once and recovers."""
        hist = _make_history([date(2024, 1, 2)], [88.5])
        mock_ticker = Mock()
        mock_ticker.history.side_effect = [pd.DataFrame(), hist]

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            price = service.get_current_price("SWKS")

        assert price == 88.5
        assert mock_ticker.history.call_count == 2

    def test_get_current_price_exception(self, service):
        """Test current price when yfinance raises."""
        mock_ticker = Mock()
        mock_ticker.history.side_effect = Exception("network error")

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            price = service.get_current_price("AAPL")

        assert price is None

    def test_get_current_price_cache(self, service):
        """Test that the in-memory cache avoids repeated requests."""
        hist = _make_history([date(2024, 1, 2)], [150.25])
        mock_ticker = Mock()
        mock_ticker.history.return_value = hist

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            p1 = service.get_current_price("AAPL")
            p2 = service.get_current_price("AAPL")

        assert p1 == p2 == 150.25
        # Only one network request should happen thanks to the cache.
        assert mock_ticker.history.call_count == 1

    def test_get_current_prices_batch(self, service):
        """Test batch fetching returns prices for all tickers."""
        tickers = ["AAPL", "MSFT", "GOOGL"]
        hist = _make_history([date(2024, 1, 2)], [150.25])
        mock_ticker = Mock()
        mock_ticker.history.return_value = hist

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            prices = service.get_current_prices(tickers)

        assert prices == {"AAPL": 150.25, "MSFT": 150.25, "GOOGL": 150.25}
        assert mock_ticker.history.call_count == 3

    def test_get_current_prices_partial_failure(self, service):
        """Test batch fetching when one ticker fails gracefully."""
        tickers = ["AAPL", "INVALID"]

        def _side_effect(ticker):
            m = Mock()
            if ticker == "AAPL":
                m.history.return_value = _make_history([date(2024, 1, 2)], [150.25])
            else:
                m.history.return_value = pd.DataFrame()
            return m

        with patch("backend.services.price_service.yf.Ticker", side_effect=_side_effect):
            prices = service.get_current_prices(tickers)

        assert prices["AAPL"] == 150.25
        assert prices["INVALID"] is None

    def test_get_current_prices_caches_batch(self, service):
        """Test that batch results are cached individually."""
        hist = _make_history([date(2024, 1, 2)], [150.25])
        mock_ticker = Mock()
        mock_ticker.history.return_value = hist

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            p1 = service.get_current_prices(["AAPL", "MSFT"])
            p2 = service.get_current_prices(["AAPL", "MSFT"])

        assert p1 == p2
        # First call fetches both; second call uses cache for both.
        assert mock_ticker.history.call_count == 2

    def test_get_current_price_cache_expiry(self):
        """Test that the cache expires after the TTL."""
        hist = _make_history([date(2024, 1, 2)], [150.25])
        mock_ticker = Mock()
        mock_ticker.history.return_value = hist

        # ttl = 0 forces a fresh fetch on every call.
        expired_service = PriceService(cache_ttl=0)
        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            expired_service.get_current_price("AAPL")
            expired_service.get_current_price("AAPL")

        assert mock_ticker.history.call_count == 2

    def test_get_historical_prices(self, service):
        """Test historical price retrieval returns (date, close) tuples."""
        dates = [date(2024, 1, 2), date(2024, 1, 3)]
        hist = _make_history(dates, [100.0, 102.5])
        mock_ticker = Mock()
        mock_ticker.history.return_value = hist

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            prices = service.get_historical_prices(
                "AAPL", start_date=date(2024, 1, 1), end_date=date(2024, 2, 1)
            )

        assert prices == [(date(2024, 1, 2), 100.0), (date(2024, 1, 3), 102.5)]
        mock_ticker.history.assert_called_once()

    def test_get_historical_prices_empty(self, service):
        """Test historical prices returns [] when no data."""
        mock_ticker = Mock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            prices = service.get_historical_prices("INVALID")

        assert prices == []

    def test_get_historical_prices_exception(self, service):
        """Test historical prices returns [] on provider failure."""
        mock_ticker = Mock()
        mock_ticker.history.side_effect = Exception("boom")

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            prices = service.get_historical_prices("AAPL")

        assert prices == []

    def test_get_price_on_date_closest_trading_day(self, service):
        """Test picking the closest available trading day."""
        # Trading days around 2023-12-29; weekday closest is the target itself.
        dates = [
            date(2023, 12, 27),
            date(2023, 12, 28),
            date(2023, 12, 29),
            date(2024, 1, 2),
            date(2024, 1, 3),
        ]
        closes = [190.0, 191.0, 192.53, 185.0, 184.0]
        hist = _make_history(dates, closes)
        mock_ticker = Mock()
        mock_ticker.history.return_value = hist

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            price = service.get_price_on_date("AAPL", date(2023, 12, 29))

        assert price == 192.53

    def test_get_price_at_fiscal_year_end_default_dec31(self, service):
        """Test fiscal year end price defaults to Dec 31 of the fiscal year."""
        dates = [date(2023, 12, 29), date(2024, 1, 2)]
        hist = _make_history(dates, [192.53, 185.0])
        mock_ticker = Mock()
        mock_ticker.history.return_value = hist

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            price = service.get_price_at_fiscal_year_end("AAPL", 2023)

        assert price == 192.53
        # The request range should span Dec 31 2023 +/- window.
        start, end = mock_ticker.history.call_args.kwargs["start"], mock_ticker.history.call_args.kwargs["end"]
        assert start <= date(2023, 12, 31) <= end

    def test_get_price_at_fiscal_year_end_custom_date(self, service):
        """Test fiscal year end price with a custom fiscal year end date."""
        dates = [date(2023, 9, 28), date(2023, 9, 29), date(2023, 10, 2)]
        hist = _make_history(dates, [170.0, 171.21, 172.0])
        mock_ticker = Mock()
        mock_ticker.history.return_value = hist

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            price = service.get_price_at_fiscal_year_end(
                "AAPL", 2023, fiscal_year_end_date=date(2023, 9, 30)
            )

        assert price == 171.21

    def test_get_price_at_fiscal_year_end_no_data(self, service):
        """Test fiscal year end price returns None when no data."""
        mock_ticker = Mock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            price = service.get_price_at_fiscal_year_end("INVALID", 2023)

        assert price is None

    def test_get_shares_outstanding(self, service):
        """Test shares outstanding from Yahoo info."""
        mock_ticker = Mock()
        mock_ticker.info = {"sharesOutstanding": 15_700_000_000}

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            shares = service.get_shares_outstanding("AAPL")

        assert shares == 15_700_000_000

    def test_get_shares_outstanding_failure(self, service):
        """Test shares outstanding returns None on failure."""
        mock_ticker = Mock()
        mock_ticker.info = {}

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            shares = service.get_shares_outstanding("AAPL")

        assert shares is None

    def test_get_split_adjustment_no_splits(self, service):
        """Test a target date with no subsequent splits."""
        mock_ticker = Mock()
        mock_splits = pd.Series(dtype=float)  # empty
        mock_ticker.splits = mock_splits

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            multiplier = service.get_split_adjustment("AAPL", date(2023, 9, 30))

        assert multiplier == 1.0

    def test_get_split_adjustment_applies_future_splits(self, service):
        """Test that splits after the target date multiply the factor."""
        splits = pd.Series(
            {datetime(2014, 6, 9): 7.0, datetime(2020, 8, 31): 4.0}
        )
        mock_ticker = Mock()
        mock_ticker.splits = splits

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            # Both splits happened after 2010 -> 7 * 4 = 28
            m2010 = service.get_split_adjustment("AAPL", date(2010, 9, 30))
            # Only the 2020 4:1 split happened after 2019.
            m2019 = service.get_split_adjustment("AAPL", date(2019, 9, 30))
            # Neither split happened after 2021 -> no adjustment.
            m2021 = service.get_split_adjustment("AAPL", date(2021, 9, 30))

        assert m2010 == pytest.approx(28.0)
        assert m2019 == pytest.approx(4.0)
        assert m2021 == pytest.approx(1.0)

    def test_get_split_adjustment_ignores_past_splits(self, service):
        """Test that splits before the target date are ignored."""
        splits = pd.Series({datetime(2014, 6, 9): 7.0})
        mock_ticker = Mock()
        mock_ticker.splits = splits

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            m_after = service.get_split_adjustment("AAPL", date(2015, 9, 30))

        assert m_after == pytest.approx(1.0)

    def test_get_split_adjustment_accepts_int_fiscal_year(self, service):
        """An integer fiscal year resolves to December 31 like the price-on-
        fiscal-year-end fallback, so an int never raises a TypeError."""
        splits = pd.Series(
            {datetime(2014, 6, 9): 7.0, datetime(2020, 8, 31): 4.0}
        )
        mock_ticker = Mock()
        mock_ticker.splits = splits

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            # 2010-12-31 is before both splits -> 7 * 4 = 28; identical to
            # passing an explicit date for the same day.
            m_int = service.get_split_adjustment("AAPL", 2010)
            m_date = service.get_split_adjustment("AAPL", date(2010, 12, 31))
            m_later = service.get_split_adjustment("AAPL", 2021)

        assert m_int == pytest.approx(28.0)
        assert m_int == m_date
        assert m_later == pytest.approx(1.0)

    def test_get_split_adjustment_failure(self, service):
        """Test that a provider failure yields 1.0 (graceful fallback)."""
        mock_ticker = Mock()
        mock_ticker.splits.side_effect = Exception("boom")

        with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
            multiplier = service.get_split_adjustment("AAPL", date(2023, 9, 30))

        assert multiplier == 1.0


if __name__ == "__main__":
    pytest.main([__file__])