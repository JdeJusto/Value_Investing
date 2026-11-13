"""Optional price providers: selection, parsing and Yahoo fallback.

No test needs a real API key: every HTTP response is mocked.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from backend.services.price_providers import (
    get_provider,
    providers_for_fetch,
    resolve_provider_name,
)
from backend.services.price_providers.fmp_provider import FMPProvider
from backend.services.price_providers.tiingo_provider import TiingoProvider
from backend.services.price_service import PriceService


@pytest.fixture(autouse=True)
def _clean_provider_env(monkeypatch):
    monkeypatch.delenv("PRICE_PROVIDER", raising=False)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_default_provider_is_yfinance():
    assert get_provider().name == "yfinance"
    assert resolve_provider_name() == "yfinance"


def test_fmp_is_selected_only_when_the_key_is_present(monkeypatch):
    monkeypatch.setenv("PRICE_PROVIDER", "fmp")
    monkeypatch.setenv("FMP_API_KEY", "dummy-key")
    assert get_provider().name == "fmp"

    monkeypatch.delenv("FMP_API_KEY")
    assert get_provider().name == "yfinance"


def test_unknown_provider_falls_back_to_yfinance(monkeypatch):
    monkeypatch.setenv("PRICE_PROVIDER", "polygon")
    assert get_provider().name == "yfinance"


def test_providers_for_fetch_orders_selected_then_other_keys(monkeypatch):
    monkeypatch.setenv("PRICE_PROVIDER", "tiingo")
    monkeypatch.setenv("TIINGO_API_KEY", "dummy-tiingo")
    monkeypatch.setenv("FMP_API_KEY", "dummy-fmp")
    assert [provider.name for provider in providers_for_fetch()] == ["tiingo", "fmp"]

    monkeypatch.delenv("FMP_API_KEY")
    assert [provider.name for provider in providers_for_fetch()] == ["tiingo"]

    monkeypatch.delenv("TIINGO_API_KEY")
    assert providers_for_fetch() == []


def test_fmp_parses_ascending_bars_and_uses_the_env_key(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "dummy-key")
    captured: dict = {}

    def fake_get(url, params=None, timeout=None):
        captured.update({"url": url, "params": params})
        return _Response(
            [
                {
                    "date": "2024-01-03",
                    "adjOpen": 101.0,
                    "adjHigh": 103.0,
                    "adjLow": 100.0,
                    "adjClose": 101.5,
                    "volume": 1000,
                },
                {
                    "date": "2024-01-02",
                    "adjOpen": 100.0,
                    "adjHigh": 102.0,
                    "adjLow": 99.0,
                    "adjClose": 100.5,
                    "volume": 900,
                },
            ]
        )

    monkeypatch.setattr(
        "backend.services.price_providers.fmp_provider.httpx.get", fake_get
    )
    bars = FMPProvider().fetch_historical("AAPL", "2024-01-01", "2024-01-05")

    assert [bar["date"] for bar in bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert [bar["close"] for bar in bars] == [100.5, 101.5]
    assert captured["params"]["apikey"] == "dummy-key"
    assert "dividend-adjusted" in captured["url"]
    assert captured["params"]["symbol"] == "AAPL"


def test_tiingo_sends_the_key_in_the_authorization_header(monkeypatch):
    monkeypatch.setenv("TIINGO_API_KEY", "dummy-tiingo")
    captured: dict = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured.update({"url": url, "headers": headers, "params": params})
        return _Response(
            [
                {
                    "date": "2024-01-02T00:00:00.000Z",
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.0,
                    "close": 101.0,
                    "adjClose": 100.5,
                    "volume": 900,
                }
            ]
        )

    monkeypatch.setattr(
        "backend.services.price_providers.tiingo_provider.httpx.get", fake_get
    )
    bars = TiingoProvider().fetch_historical("AAPL", "2024-01-01", "2024-01-05")

    assert bars[0]["date"] == date(2024, 1, 2)
    assert bars[0]["close"] == 100.5
    assert captured["headers"]["Authorization"] == "Token dummy-tiingo"
    assert "AAPL" in captured["url"]


def test_provider_error_messages_redact_the_key(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "dummy-secret-key")

    def fake_get(url, params=None, timeout=None):
        raise RuntimeError("connection to dummy-secret-key failed")

    monkeypatch.setattr(
        "backend.services.price_providers.fmp_provider.httpx.get", fake_get
    )
    with pytest.raises(RuntimeError) as excinfo:
        FMPProvider().fetch_historical("AAPL", "2024-01-01", "2024-01-05")
    assert "dummy-secret-key" not in str(excinfo.value)
    assert "***" in str(excinfo.value)


def test_price_service_falls_back_to_yahoo_when_the_provider_fails(monkeypatch):
    class _FailingProvider:
        name = "fmp"

        def fetch_historical(self, ticker, start, end):
            raise RuntimeError("provider down")

    monkeypatch.setattr(
        "backend.services.price_providers.providers_for_fetch",
        lambda name=None: [_FailingProvider()],
    )

    frame = pd.DataFrame(
        {"Close": [150.0, 151.0]},
        index=pd.DatetimeIndex(
            [
                datetime(2024, 1, 2, tzinfo=UTC),
                datetime(2024, 1, 3, tzinfo=UTC),
            ]
        ),
    )

    class _Ticker:
        def history(self, **kwargs):
            return frame

    monkeypatch.setattr(
        "backend.services.price_service.yf.Ticker", lambda ticker: _Ticker()
    )
    prices = PriceService()._fetch_historical_prices(
        "AAPL", date(2024, 1, 1), date(2024, 1, 5)
    )

    assert prices == [(date(2024, 1, 2), 150.0), (date(2024, 1, 3), 151.0)]
