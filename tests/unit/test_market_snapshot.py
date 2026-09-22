"""Unit tests for the market-snapshot path (PriceService.get_market_snapshots
+ SnapshotMarketProvider) used to make batch analysis network-free."""

from unittest.mock import Mock, patch

import pytest

from backend.providers.snapshot import SnapshotMarketProvider
from backend.services.price_service import PriceService

_INFO = {
    "regularMarketPrice": 150.25,
    "marketCap": 2_300_000_000_000,
    "enterpriseValue": 2_400_000_000_000,
    "beta": 1.24,
    "sharesOutstanding": 15_300_000_000,
    "longName": "Apple Inc.",
}


def _fake_info(info):
    t = Mock()
    t.info = info
    return t


class TestGetMarketSnapshots:
    def test_fetches_snapshot_and_warms_price_cache(self):
        service = PriceService()
        with patch(
            "backend.services.price_service.yf.Ticker",
            return_value=_fake_info(_INFO),
        ):
            snapshots = service.get_market_snapshots(
                ["AAPL"], batch_size=1, delay=0
            )

        assert snapshots["AAPL"]["marketCap"] == 2_300_000_000_000
        # The derived price/shares are warmed into the memory cache so
        # downstream PriceService reads reuse identical values.
        assert service.get_current_price("AAPL") == 150.25
        assert service.get_shares_outstanding("AAPL") == 15_300_000_000

    def test_failure_returns_none(self):
        service = PriceService()
        t = Mock()
        t.info = None
        t2 = Mock()
        t2.info = None
        with patch(
            "backend.services.price_service.yf.Ticker",
            side_effect=[t, t2],
        ):
            snapshots = service.get_market_snapshots(
                ["ZZZZ"], batch_size=1, delay=0
            )
        assert snapshots["ZZZZ"] is None


class TestPriceFailureClassification:
    """Categorize failed quote fetches (glitch vs mapping vs delisted)."""

    @pytest.fixture(autouse=True)
    def no_sleep(self):
        with patch("backend.services.price_service.time.sleep"):
            yield

    @staticmethod
    def _quote(info):
        t = Mock()
        t.info = info
        return t

    def test_data_available_on_retry_is_a_glitch(self):
        service = PriceService()
        with patch(
            "backend.services.price_service.yf.Ticker",
            side_effect=[self._quote({"quoteType": "EQUITY"})],
        ):
            category = service.classify_price_failure(
                "ON", known_ticker=lambda _: True
            )
        assert category == "yahoo_glitch"

    def test_no_data_and_unknown_listing_is_mapping(self):
        service = PriceService()
        ticker = Mock()
        ticker.info = None
        hist = Mock()
        hist.empty = True
        side_effect = [ticker, ticker]
        with patch(
            "backend.services.price_service.yf.Ticker",
            side_effect=side_effect,
        ) as t:
            t.return_value.history.return_value = hist
            category = service.classify_price_failure(
                "ZZZZQQ", known_ticker=lambda _: False
            )
        assert category == "mapping"

    def test_no_data_and_active_listing_is_delisted(self):
        service = PriceService()
        ticker = Mock()
        ticker.info = None
        hist = Mock()
        hist.empty = True
        with patch(
            "backend.services.price_service.yf.Ticker",
            side_effect=[ticker, ticker],
        ) as t:
            t.return_value.history.return_value = hist
            category = service.classify_price_failure(
                "DED", known_ticker=lambda _: True
            )
        assert category == "delisted"

    def test_no_data_and_no_listing_opinion_is_unknown(self):
        service = PriceService()
        ticker = Mock()
        ticker.info = None
        hist = Mock()
        hist.empty = True
        with patch(
            "backend.services.price_service.yf.Ticker",
            side_effect=[ticker, ticker],
        ) as t:
            t.return_value.history.return_value = hist
            category = service.classify_price_failure("MYST")
        assert category == "unknown"

    def test_history_fallback_also_means_glitch(self):
        """.info returns nothing but the chart endpoint responds: glitch."""
        service = PriceService()
        ticker = Mock()
        ticker.info = None
        hist = Mock()
        hist.empty = False
        third = Mock()
        third.history.return_value = hist
        with patch(
            "backend.services.price_service.yf.Ticker",
            side_effect=[ticker, ticker, third],
        ):
            category = service.classify_price_failure(
                "ON", known_ticker=lambda _: True
            )
        assert category == "yahoo_glitch"

    def test_empty_info_dict_is_not_data(self):
        """.info={} (no quoteType) is treated as no data, not a glitch."""
        service = PriceService()
        ticker = Mock()
        ticker.info = {}
        hist = Mock()
        hist.empty = True
        with patch(
            "backend.services.price_service.yf.Ticker",
            side_effect=[ticker, ticker],
        ) as t:
            t.return_value.history.return_value = hist
            category = service.classify_price_failure(
                "JUNK", known_ticker=lambda _: False
            )
        assert category == "mapping"

class TestSnapshotMarketProvider:
    def test_serves_all_market_fields_from_snapshot(self):
        provider = SnapshotMarketProvider({"AAPL": dict(_INFO)})
        assert provider.get_current_price("AAPL") == 150.25
        assert provider.get_market_cap("AAPL") == 2_300_000_000_000
        assert provider.get_enterprise_value("AAPL") == 2_400_000_000_000
        assert provider.get_beta("AAPL") == 1.24
        assert provider.get_shares_outstanding("AAPL") == 15_300_000_000
        assert provider.get_company_name("AAPL") == "Apple Inc."

    def test_missing_ticker_falls_back_gracefully(self):
        provider = SnapshotMarketProvider({"AAPL": dict(_INFO)})
        # No fallback provider: absent tickers degrade to None (analysis runs
        # with the valuation fields N/A) instead of hitting the network.
        assert provider.get_market_cap("MSFT") is None
        assert provider.get_current_price("MSFT") is None

    def test_fallback_provider_used_only_for_absent_tickers(self):
        fallback = Mock()
        fallback.get_beta.return_value = 0.9
        provider = SnapshotMarketProvider({"AAPL": dict(_INFO)}, fallback=fallback)
        # Present ticker: served from the snapshot, never delegates.
        assert provider.get_beta("AAPL") == 1.24
        fallback.get_beta.assert_not_called()
        # Absent ticker: delegated to the fallback provider.
        assert provider.get_beta("MSFT") == 0.9
        fallback.get_beta.assert_called_once_with("MSFT")

    def test_none_fields_are_real_values_not_network_calls(self):
        info = {k: v for k, v in _INFO.items()}
        info["beta"] = None
        fallback = Mock()
        provider = SnapshotMarketProvider({"AAPL": info}, fallback=fallback)
        assert provider.get_beta("AAPL") is None
        # A snapshotted ticker with a missing field must NOT fall back to the
        # network (analysis must stay network-free); absent tickers only.
        fallback.get_beta.assert_not_called()

    @pytest.mark.parametrize(
        "field_getter",
        [
            ("market_cap", "marketCap"),
            ("enterprise_value", "enterpriseValue"),
            ("beta", "beta"),
            ("shares_outstanding", "sharesOutstanding"),
        ],
    )
    def test_field_mapping(self, field_getter):
        field, info_key = field_getter
        provider = SnapshotMarketProvider({"X": {info_key: 42}})
        assert getattr(provider, f"get_{field}")("x") == 42