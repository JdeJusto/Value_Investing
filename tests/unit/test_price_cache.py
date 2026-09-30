"""PriceCache: batch prefetch, TTL, per-ticker fallback, thread safety."""

from __future__ import annotations

import threading

import pytest

from backend.services.price_cache import PriceCache


class _Service:
    """Stub PriceService with batch and per-ticker counters."""

    def __init__(self, batch=None, per_ticker=None, batch_fails=False):
        self._batch = batch or {}
        self._per = per_ticker or {}
        self._batch_fails = batch_fails
        self.batch_calls: list[list[str]] = []
        self.per_calls: list[str] = []

    def get_current_prices(self, tickers):
        self.batch_calls.append(list(tickers))
        if self._batch_fails:
            raise RuntimeError("yahoo batch down")
        return {t: self._batch.get(t) for t in tickers}

    def get_current_price(self, ticker):
        self.per_calls.append(ticker)
        return self._per.get(ticker, self._batch.get(ticker))


def test_prefetch_populates_the_cache_in_one_batch():
    service = _Service(batch={"AAPL": 100.0, "KO": 60.0})
    cache = PriceCache(service=service)
    cache.prefetch(["AAPL", "KO"])
    assert len(service.batch_calls) == 1
    assert cache.get("AAPL") == 100.0
    assert cache.get("KO") == 60.0
    assert service.per_calls == []  # no per-ticker calls needed


def test_prefetch_skips_fresh_entries():
    service = _Service(batch={"AAPL": 100.0})
    cache = PriceCache(service=service)
    cache.prefetch(["AAPL"])
    cache.prefetch(["AAPL", "MSFT"])
    assert service.batch_calls == [["AAPL"], ["MSFT"]]


def test_get_within_ttl_does_not_refetch():
    service = _Service(batch={"AAPL": 100.0})
    cache = PriceCache(service=service)
    cache.prefetch(["AAPL"])
    assert cache.get("AAPL") == 100.0
    assert service.per_calls == []


def test_expired_entry_triggers_a_refetch(monkeypatch):
    service = _Service(batch={"AAPL": 100.0}, per_ticker={"AAPL": 111.0})
    cache = PriceCache(ttl=10, service=service)
    clock = {"now": 1_000.0}
    monkeypatch.setattr(
        "backend.services.price_cache.time.monotonic", lambda: clock["now"]
    )
    cache.prefetch(["AAPL"])
    assert cache.get("AAPL") == 100.0
    clock["now"] += 11  # TTL elapsed
    assert cache.get("AAPL") == 111.0
    assert service.per_calls == ["AAPL"]


def test_batch_failure_falls_back_to_per_ticker():
    service = _Service(batch={"AAPL": 100.0}, batch_fails=True)
    cache = PriceCache(service=service)
    cache.prefetch(["AAPL"])
    assert service.batch_calls == [["AAPL"]]
    assert service.per_calls == ["AAPL"]
    assert cache.get("AAPL") == 100.0


def test_missing_quote_is_cached_as_none():
    service = _Service(batch={})
    cache = PriceCache(service=service)
    cache.prefetch(["ZZZZ"])
    assert cache.get("ZZZZ") is None
    assert service.per_calls == []  # the batch already said "no quote"


def test_concurrent_access_is_thread_safe():
    service = _Service(batch={"AAPL": 100.0, "KO": 60.0})
    cache = PriceCache(service=service)
    results: dict[str, float | None] = {}
    errors: list[Exception] = []

    def worker(ticker: str) -> None:
        try:
            results[ticker] = cache.get(ticker)
        except Exception as exc:  # noqa: BLE001 — the test reports it
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(ticker,)) for ticker in ("AAPL", "KO") * 5
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert results == {"AAPL": 100.0, "KO": 60.0}
    # The batch is not re-fetched by concurrent gets (each ticker at most once
    # per thread, but the values must be correct and stable).
    assert all(value in (100.0, 60.0) for value in results.values())
    assert len(cache) == 2


def test_prefetch_empty_list_is_a_noop():
    service = _Service()
    cache = PriceCache(service=service)
    cache.prefetch([])
    assert service.batch_calls == []


@pytest.mark.parametrize("ticker", ["aapl", "AAPL"])
def test_tickers_are_normalised(ticker):
    service = _Service(batch={"AAPL": 100.0})
    cache = PriceCache(service=service)
    cache.prefetch([ticker])
    assert cache.get("aapl") == 100.0
