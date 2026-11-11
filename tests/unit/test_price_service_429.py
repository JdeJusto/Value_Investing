"""yfinance retry, pacing, disk cache and the 429 reason surfaced by refresh."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.services import price_service as ps
from backend.services.price_service import PriceService
from backend.services.ticker_refresh_service import refresh_ticker


class _HttpError(Exception):
    """Stand-in for the requests/yfinance HTTP error (keeps the test hermetic)."""


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(ps.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(ps, "MIN_REQUEST_INTERVAL", 0.0)


def test_yf_call_retries_429_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise _HttpError("429 Too Many Requests")
        return "ok"

    assert ps._yf_call(flaky) == "ok"
    assert len(calls) == 3


def test_yf_call_gives_up_after_three_attempts():
    calls = []

    def always_429():
        calls.append(1)
        raise _HttpError("429 Too Many Requests")

    with pytest.raises(_HttpError, match="429"):
        ps._yf_call(always_429)
    assert len(calls) == ps.RETRY_ATTEMPTS


def test_401_is_not_retried():
    calls = []

    def unauthorized():
        calls.append(1)
        raise _HttpError("401 Unauthorized / invalid crumb")

    with pytest.raises(_HttpError, match="401"):
        ps._yf_call(unauthorized)
    assert len(calls) == 1


def test_current_price_records_the_rate_limit_reason(monkeypatch):
    class _Ticker:
        def history(self, **_kwargs):
            raise _HttpError("429 Too Many Requests")

    monkeypatch.setattr(ps, "yf", SimpleNamespace(Ticker=lambda _ticker: _Ticker()))
    service = PriceService()

    assert service._fetch_current_price("AAPL") is None
    assert service.get_last_error("AAPL") == ps.RATE_LIMIT_REASON


def test_disk_cache_hit_avoids_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "DISK_CACHE_ENABLED", True)
    monkeypatch.setattr(ps, "DISK_CACHE_DIR", tmp_path)
    calls = []

    def fake_fetch(self, ticker, start_date=None, end_date=None):
        calls.append(ticker)
        return [(date(2020, 6, 30), 100.0)]

    monkeypatch.setattr(PriceService, "_fetch_historical_prices", fake_fetch)
    first = PriceService()
    assert first.get_historical_prices("AAPL", date(2020, 1, 1), date(2020, 12, 31))

    second = PriceService()
    prices = second.get_historical_prices("AAPL", date(2020, 1, 1), date(2020, 12, 31))
    assert prices == [(date(2020, 6, 30), 100.0)]
    assert calls == ["AAPL"]  # the second service read the disk, not Yahoo


def test_disk_cache_miss_fetches(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "DISK_CACHE_ENABLED", True)
    monkeypatch.setattr(ps, "DISK_CACHE_DIR", tmp_path / "empty")
    calls = []

    def fake_fetch(self, ticker, start_date=None, end_date=None):
        calls.append(ticker)
        return [(date(2020, 6, 30), 100.0)]

    monkeypatch.setattr(PriceService, "_fetch_historical_prices", fake_fetch)
    service = PriceService()
    service.get_historical_prices("MSFT", date(2020, 1, 1), date(2020, 12, 31))
    assert calls == ["MSFT"]


def test_recent_disk_cache_expires_after_one_day(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "DISK_CACHE_ENABLED", True)
    monkeypatch.setattr(ps, "DISK_CACHE_DIR", tmp_path)
    calls = []

    def fake_fetch(self, ticker, start_date=None, end_date=None):
        calls.append(ticker)
        return [(datetime.now(UTC).date(), 100.0)]

    monkeypatch.setattr(PriceService, "_fetch_historical_prices", fake_fetch)
    end = datetime.now(UTC).date()
    PriceService().get_historical_prices("AAPL", end - timedelta(days=5), end)
    cache_file = next(tmp_path.glob("*.json"))
    old = ps.time.time() - ps.DISK_CACHE_RECENT_TTL_SECONDS - 60
    os.utime(cache_file, (old, old))

    PriceService().get_historical_prices("AAPL", end - timedelta(days=5), end)
    assert calls == ["AAPL", "AAPL"]  # expired -> network again


def test_refresh_surfaces_the_rate_limit_reason():
    class _Prices:
        def get_last_error(self, _ticker):
            return ps.RATE_LIMIT_REASON

    class _Refresh:
        _price_service = _Prices()

        def ensure_fresh_and_prices(self, *_args, **_kwargs):
            return SimpleNamespace(
                refreshed=[],
                skipped=[],
                failed=[],
                prices={},
                sec_skipped_reason=None,
            )

    result = refresh_ticker("AAPL", facts=False, prices=True, service=_Refresh())

    assert result.prices_synced is False
    assert result.prices_error == ps.RATE_LIMIT_REASON


def test_disk_cache_path_never_embeds_the_raw_ticker(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "DISK_CACHE_DIR", tmp_path)

    path = ps._disk_cache_path("../../etc/passwd", None, None)

    assert path.parent == tmp_path
    assert ".." not in path.name
    assert "PASSWD" not in path.name


def test_disk_cache_path_is_deterministic_and_ticker_specific(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "DISK_CACHE_DIR", tmp_path)

    first = ps._disk_cache_path("AAPL", date(2020, 1, 1), date(2020, 12, 31))
    same = ps._disk_cache_path("aapl", date(2020, 1, 1), date(2020, 12, 31))
    other = ps._disk_cache_path("MSFT", date(2020, 1, 1), date(2020, 12, 31))

    assert first == same
    assert first != other
    assert first.parent == tmp_path


def test_disk_cache_rejects_an_empty_ticker(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(ps, "DISK_CACHE_ENABLED", True)
    monkeypatch.setattr(ps, "DISK_CACHE_DIR", tmp_path)

    with pytest.raises(ValueError):
        ps._disk_cache_path("", None, None)
    assert ps._disk_cache_get("", None, None) is None
