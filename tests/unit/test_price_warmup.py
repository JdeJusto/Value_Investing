"""Shared price warm-up: the analysis batch fetch runs concurrently."""

from __future__ import annotations

import threading
import time

from backend.services.price_service import PriceService
from backend.services.refresh_service import RefreshService


class _RecordingService:
    """Captures the batch call arguments and returns canned prices."""

    def __init__(self):
        self.calls: list[dict] = []

    def get_current_prices(self, tickers, **kwargs):
        self.calls.append({"tickers": list(tickers), **kwargs})
        return {ticker: 100.0 for ticker in tickers}


def test_fetch_prices_passes_bounded_workers():
    service = _RecordingService()
    refresh = RefreshService(price_service=service)
    prices = refresh._fetch_prices(["AAPL", "MSFT", "KO", "XOM", "F"])
    assert prices["AAPL"] == 100.0
    assert service.calls[0]["workers"] == RefreshService.PRICE_WARMUP_WORKERS


def test_single_ticker_uses_one_worker():
    service = _RecordingService()
    RefreshService(price_service=service)._fetch_prices(["AAPL"])
    assert service.calls[0]["workers"] == 1


def test_batch_failure_never_breaks_the_command():
    class _Boom:
        def get_current_prices(self, tickers, **kwargs):
            raise RuntimeError("yahoo down")

    assert RefreshService(price_service=_Boom())._fetch_prices(["AAPL"]) == {}


def test_real_batch_honours_workers(monkeypatch):
    """The real PriceService runs the per-ticker fetches concurrently."""
    concurrency = {"now": 0, "max": 0}
    lock = threading.Lock()

    def slow_price(ticker: str):
        with lock:
            concurrency["now"] += 1
            concurrency["max"] = max(concurrency["max"], concurrency["now"])
        time.sleep(0.05)
        with lock:
            concurrency["now"] -= 1
        return 100.0

    service = PriceService()
    monkeypatch.setattr(service, "get_current_price", slow_price)
    prices = service.get_current_prices(["AAPL", "MSFT", "KO"], workers=3)
    assert prices == {"AAPL": 100.0, "MSFT": 100.0, "KO": 100.0}
    assert concurrency["max"] >= 2
