"""Yahoo bulk price fetch and the provider circuit breaker."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from backend.services.price_providers import CircuitBreaker
from backend.services.price_service import PriceService


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
def test_breaker_opens_after_three_rate_limit_errors():
    breaker = CircuitBreaker(threshold=3, cooldown_seconds=60)
    for _ in range(3):
        breaker.record_failure("tiingo", RuntimeError("429 Too Many Requests"))

    assert breaker.is_open("tiingo") is True


def test_breaker_ignores_non_rate_limit_errors():
    breaker = CircuitBreaker(threshold=3, cooldown_seconds=60)
    for _ in range(10):
        breaker.record_failure("fmp", RuntimeError("500 Server Error"))

    assert breaker.is_open("fmp") is False


def test_breaker_closes_after_cooldown_without_sleeping():
    now = [0.0]
    breaker = CircuitBreaker(threshold=2, cooldown_seconds=30, clock=lambda: now[0])
    breaker.record_failure("tiingo", RuntimeError("403 Forbidden"))
    breaker.record_failure("tiingo", RuntimeError("403 Forbidden"))
    assert breaker.is_open("tiingo") is True

    now[0] = 31.0
    assert breaker.is_open("tiingo") is False


def test_breaker_success_resets_the_counter():
    breaker = CircuitBreaker(threshold=2, cooldown_seconds=60)
    breaker.record_failure("tiingo", RuntimeError("429"))
    breaker.record_success("tiingo")
    breaker.record_failure("tiingo", RuntimeError("429"))

    assert breaker.is_open("tiingo") is False


def test_breaker_logs_once_per_outage(caplog):
    breaker = CircuitBreaker(threshold=2, cooldown_seconds=60)
    with caplog.at_level("WARNING", logger="backend.price_providers"):
        for _ in range(10):
            breaker.record_failure("tiingo", RuntimeError("429 Too Many Requests"))

    messages = [record.message for record in caplog.records]
    assert len(messages) == 1
    assert "Circuit breaker OPEN for tiingo" in messages[0]


# ---------------------------------------------------------------------------
# Batch prices
# ---------------------------------------------------------------------------
def _multi_close_frame():
    columns = pd.MultiIndex.from_product([["Close"], ["AAPL", "MSFT"]])
    return pd.DataFrame(
        [[150.0, 300.0]],
        index=pd.DatetimeIndex([datetime(2026, 11, 12, tzinfo=UTC)]),
        columns=columns,
    )


def test_batch_prices_uses_one_yahoo_download(monkeypatch):
    calls: list[list[str]] = []

    def fake_download(tickers, **kwargs):
        calls.append(list(tickers))
        return _multi_close_frame()

    monkeypatch.setattr("backend.services.price_service.yf.download", fake_download)
    prices = PriceService().get_batch_prices(["AAPL", "MSFT"])

    assert prices == {"AAPL": 150.0, "MSFT": 300.0}
    assert calls == [["AAPL", "MSFT"]]


def test_batch_prices_reuses_the_memory_cache(monkeypatch):
    calls = []

    def fake_download(tickers, **kwargs):
        calls.append(list(tickers))
        return _multi_close_frame()

    monkeypatch.setattr("backend.services.price_service.yf.download", fake_download)
    service = PriceService()
    service.get_batch_prices(["AAPL", "MSFT"])
    prices = service.get_batch_prices(["AAPL", "MSFT"])

    assert prices == {"AAPL": 150.0, "MSFT": 300.0}
    assert len(calls) == 1


def test_batch_failure_does_not_cascade_per_ticker(monkeypatch):
    def fake_download(tickers, **kwargs):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr("backend.services.price_service.yf.download", fake_download)
    monkeypatch.setattr(
        PriceService,
        "get_current_price",
        lambda self, ticker: pytest.fail("per-ticker fallback must not run"),
    )
    prices = PriceService().get_batch_prices(["AAPL", "MSFT"])

    assert prices == {"AAPL": None, "MSFT": None}


def test_batch_falls_back_only_for_missing_names(monkeypatch):
    frame = _multi_close_frame()
    frame[("Close", "MSFT")] = float("nan")

    def fake_download(tickers, **kwargs):
        return frame

    monkeypatch.setattr("backend.services.price_service.yf.download", fake_download)
    service = PriceService()
    monkeypatch.setattr(
        service, "get_current_price", lambda ticker: 999.0 if ticker == "MSFT" else None
    )
    prices = service.get_batch_prices(["AAPL", "MSFT"])

    assert prices == {"AAPL": 150.0, "MSFT": 999.0}


def test_single_ticker_batch_frame_is_parsed(monkeypatch):
    frame = pd.DataFrame(
        {"Close": [149.0, 150.0]},
        index=pd.DatetimeIndex(
            [datetime(2026, 11, 11, tzinfo=UTC), datetime(2026, 11, 12, tzinfo=UTC)]
        ),
    )
    monkeypatch.setattr(
        "backend.services.price_service.yf.download",
        lambda tickers, **kwargs: frame,
    )
    assert PriceService().get_batch_prices(["AAPL"]) == {"AAPL": 150.0}
