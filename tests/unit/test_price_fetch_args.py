"""Price fetch args: one cached full-history fetch serves every lookup.

Covers the historical-valuation fix: the fiscal-year-end helpers must work
without an explicit window and reuse a single ``history()`` call per ticker.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import Mock, patch

import pandas as pd

from backend.services.price_service import PriceService


def _make_history(dates, closes):
    return pd.DataFrame(
        {"Close": closes},
        index=pd.DatetimeIndex(
            [datetime.combine(d, datetime.min.time()) for d in dates]
        ),
    )


def test_fetch_without_explicit_window():
    # fiscal_year_end_date=None defaults to Dec 31 and uses the full fetch.
    hist = _make_history([date(2023, 12, 29), date(2024, 1, 2)], [192.53, 185.0])
    mock_ticker = Mock()
    mock_ticker.history.return_value = hist

    with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
        price = PriceService().get_price_at_fiscal_year_end("AAPL", 2023)

    assert price == 192.53
    assert "end" not in mock_ticker.history.call_args.kwargs


def test_fetch_with_specific_date():
    hist = _make_history(
        [date(2023, 9, 28), date(2023, 9, 29), date(2023, 10, 2)],
        [170.0, 171.21, 172.0],
    )
    mock_ticker = Mock()
    mock_ticker.history.return_value = hist

    with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
        price = PriceService().get_price_at_fiscal_year_end(
            "AAPL", 2023, fiscal_year_end_date=date(2023, 9, 30)
        )

    assert price == 171.21


def test_one_history_call_per_ticker_per_session():
    hist = _make_history([date(2022, 12, 30), date(2023, 12, 29)], [129.93, 192.53])
    mock_ticker = Mock()
    mock_ticker.history.return_value = hist
    service = PriceService()

    with patch("backend.services.price_service.yf.Ticker", return_value=mock_ticker):
        assert service.get_price_at_fiscal_year_end("AAPL", 2023) == 192.53
        assert service.get_price_at_fiscal_year_end("AAPL", 2022) == 129.93
        # No price within the window for 2021 -> None, still one fetch.
        assert service.get_price_at_fiscal_year_end("AAPL", 2021) is None

    assert mock_ticker.history.call_count == 1
