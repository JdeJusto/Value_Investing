"""Unit tests for the Yahoo availability preflight (hermetic, no network)."""

from __future__ import annotations

import pytest

from backend.services.yahoo_health import (
    YAHOO_HEALTH_URL,
    YahooHealth,
    check_yahoo_availability,
    reset_yahoo_health_cache,
)


@pytest.fixture(autouse=True)
def _clean_state():
    reset_yahoo_health_cache()
    yield
    reset_yahoo_health_cache()


def _ok(url, timeout):
    return YahooHealth(True, "ok", 200, 0.0)


def _down(reason, status=None):
    def inner(url, timeout):
        return YahooHealth(False, reason, status, 0.0)

    return inner


def test_available_when_probe_succeeds():
    health = check_yahoo_availability(probe=_ok)
    assert health.available is True
    assert health.http_status == 200


def test_probe_shortcut_uses_the_injected_probe(monkeypatch):
    monkeypatch.setattr(
        "backend.services.yahoo_health.check_yahoo_availability",
        lambda **kwargs: YahooHealth(True, "ok", 200, 0.0),
    )
    from backend.services import yahoo_health

    assert yahoo_health.probe(force=True) is True


def test_unavailable_reports_the_reason():
    health = check_yahoo_availability(probe=_down("Yahoo returned HTTP 429", 429))
    assert health.available is False
    assert "429" in health.reason
    assert health.http_status == 429


def test_retries_once_before_giving_up():
    calls = []

    def flaky(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            return YahooHealth(False, "timeout", None, 0.0)
        return YahooHealth(True, "ok", 200, 0.0)

    health = check_yahoo_availability(probe=flaky, retry_delay=0.0)
    assert health.available is True
    assert len(calls) == 2


def test_probe_that_raises_is_unavailable_not_fatal():
    def broken(url, timeout):
        raise RuntimeError("socket exploded")

    health = check_yahoo_availability(probe=broken, attempts=1, retry_delay=0.0)
    assert health.available is False
    assert "socket exploded" in health.reason


def test_result_is_cached_for_the_ttl(monkeypatch):
    calls = []

    def counting(url, timeout):
        calls.append(url)
        return YahooHealth(True, "ok", 200, 0.0)

    check_yahoo_availability(probe=counting, ttl=120.0)
    check_yahoo_availability(probe=counting, ttl=120.0)
    assert len(calls) == 1  # second call served from the cache

    check_yahoo_availability(probe=counting, ttl=120.0, force=True)
    assert len(calls) == 2  # force bypasses the cache


def test_expired_cache_triggers_a_new_probe():
    calls = []

    def counting(url, timeout):
        calls.append(url)
        return YahooHealth(True, "ok", 200, 0.0)

    check_yahoo_availability(probe=counting, ttl=0.0)
    check_yahoo_availability(probe=counting, ttl=0.0)
    assert len(calls) == 2


def test_env_ttl_and_timeout(monkeypatch):
    monkeypatch.setenv("YAHOO_HEALTH_TTL_SECONDS", "42")
    monkeypatch.setenv("YAHOO_HEALTH_TIMEOUT_SECONDS", "1.5")
    seen = {}

    def capture(url, timeout):
        seen["url"] = url
        seen["timeout"] = timeout
        return YahooHealth(True, "ok", 200, 0.0)

    check_yahoo_availability(probe=capture)
    assert seen["url"] == YAHOO_HEALTH_URL
    assert seen["timeout"] == 1.5

    # TTL is read from the environment on the next (uncached) call.
    reset_yahoo_health_cache()
    check_yahoo_availability(probe=capture)
    assert len(seen) == 2


def test_invalid_env_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("YAHOO_HEALTH_TIMEOUT_SECONDS", "not-a-number")
    seen = {}

    def capture(url, timeout):
        seen["timeout"] = timeout
        return YahooHealth(True, "ok", 200, 0.0)

    from backend.services.yahoo_health import DEFAULT_TIMEOUT_SECONDS

    check_yahoo_availability(probe=capture)
    assert seen["timeout"] == DEFAULT_TIMEOUT_SECONDS


def test_cached_health_exposes_the_last_result_without_http():
    from backend.services.yahoo_health import cached_yahoo_health

    assert cached_yahoo_health() is None
    check_yahoo_availability(probe=_down("Yahoo returned HTTP 429", 429))
    cached = cached_yahoo_health()
    assert cached is not None
    assert cached.available is False
    assert "429" in cached.reason


def test_fetches_short_circuit_once_yahoo_is_known_down(monkeypatch):
    """A down Yahoo must not burn three attempts (plus backoff) per ticker."""
    import time as time_module

    from backend.services.price_service import PriceService

    def _boom(*args, **kwargs):
        raise AssertionError("no HTTP call may happen once Yahoo is known down")

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _boom)
    monkeypatch.setattr(time_module, "sleep", lambda *_: None)

    check_yahoo_availability(probe=_down("Yahoo returned HTTP 429", 429), force=True)
    service = PriceService(health_fn=check_yahoo_availability)

    assert service._fetch_market_snapshot("AAPL") is None
    assert service._fetch_current_price("AAPL") is None
    assert service.get_market_snapshots(["AAPL", "KO"]) == {}


# ----------------------------------------------------------------------
# the outcome must be readable by the caller (429 watcher contract)
# ----------------------------------------------------------------------


def test_last_health_is_none_before_any_probe():
    from backend.services.price_service import PriceService
    from backend.services.yahoo_health import YahooHealth

    service = PriceService(health_fn=lambda **kwargs: YahooHealth(True, "ok", 200, 0.0))
    assert service.last_health() is None  # a method, called — never the bound method


def test_last_health_exposes_the_probe_result():
    from backend.services.price_service import PriceService
    from backend.services.yahoo_health import YahooHealth

    down = YahooHealth(False, "Yahoo returned HTTP 429 (rate limited)", 429, 0.0)
    service = PriceService(health_fn=lambda **kwargs: down)

    assert service.yahoo_available().available is False
    assert service.last_health() is down
    assert service.last_health().available is False
    assert service.last_health().http_status == 429


def test_probe_user_agent_is_configurable(monkeypatch):
    """The agent is configurable and defaults to the minimal one."""
    from backend.services.yahoo_health import DEFAULT_USER_AGENT, _user_agent

    monkeypatch.delenv("YAHOO_HEALTH_USER_AGENT", raising=False)
    assert _user_agent() == DEFAULT_USER_AGENT == "Mozilla/5.0"

    monkeypatch.setenv("YAHOO_HEALTH_USER_AGENT", "CustomTool/1.0")
    assert _user_agent() == "CustomTool/1.0"

    # An empty override must not produce an empty header.
    monkeypatch.setenv("YAHOO_HEALTH_USER_AGENT", "   ")
    assert _user_agent() == DEFAULT_USER_AGENT


# ----------------------------------------------------------------------
# the probe walks the real path (yfinance)
# ----------------------------------------------------------------------


class _FakeTicker:
    def __init__(self, symbol, info=None, error=None):
        self._symbol = symbol
        self._info = info
        self._error = error

    @property
    def fast_info(self):
        if self._error is not None:
            raise self._error
        return self._info


def _patch_yfinance(monkeypatch, **kwargs):
    created = []

    def _ticker(symbol):
        created.append(symbol)
        return _FakeTicker(symbol, **kwargs)

    import sys
    import types

    module = types.ModuleType("yfinance")
    module.Ticker = _ticker
    monkeypatch.setitem(sys.modules, "yfinance", module)
    return created


def test_probe_succeeds_when_the_full_path_works(monkeypatch):
    _patch_yfinance(monkeypatch, info={"lastPrice": 341.07})
    reset_yahoo_health_cache()

    health = check_yahoo_availability(force=True)

    assert health.available is True
    assert health.stage == "yfinance"
    assert health.crumb is True
    assert health.non_transient is False


def test_probe_fails_when_the_crumb_is_rate_limited(monkeypatch):
    """yfinance raises YFRateLimitError on a 429 crumb fetch."""
    from yfinance.exceptions import YFRateLimitError

    _patch_yfinance(monkeypatch, error=YFRateLimitError())
    reset_yahoo_health_cache()

    health = check_yahoo_availability(force=True)

    assert health.available is False
    assert health.http_status == 429
    assert health.stage == "yfinance"
    assert health.rate_limited is True
    assert health.non_transient is True


def test_probe_fails_when_the_session_is_rejected(monkeypatch):
    """An unusable crumb shows up as 401 Invalid Crumb."""
    _patch_yfinance(monkeypatch, error=RuntimeError("Invalid Crumb"))
    reset_yahoo_health_cache()

    health = check_yahoo_availability(force=True)

    assert health.available is False
    assert health.http_status == 401
    assert health.non_transient is True
    assert "crumb" in health.reason.lower()


def test_probe_reports_an_empty_quote_as_unavailable(monkeypatch):
    _patch_yfinance(monkeypatch, info={})
    reset_yahoo_health_cache()

    health = check_yahoo_availability(force=True)

    assert health.available is False
    assert health.stage == "yfinance"


def test_probe_stages_are_distinct(monkeypatch):
    """A failure names the step, so 'unavailable' is never anonymous."""
    from backend.services.yahoo_health import (
        STAGE_COOKIE,
        STAGE_CRUMB,
        STAGE_QUOTE,
        STAGE_YFINANCE,
    )

    assert len({STAGE_COOKIE, STAGE_CRUMB, STAGE_QUOTE, STAGE_YFINANCE}) == 4

    # An injected probe keeps whatever stage it reports.
    def _probe_with_stage(timeout):
        return YahooHealth(False, "boom", 503, 0.0, stage=STAGE_QUOTE)

    reset_yahoo_health_cache()
    health = check_yahoo_availability(probe=_probe_with_stage, force=True)
    assert health.stage == STAGE_QUOTE


def test_non_transient_failures_are_not_retried(monkeypatch):
    """Retrying a 429 is what turns one refusal into a throttle."""
    calls = []

    def _rate_limited(timeout):
        calls.append(timeout)
        return YahooHealth(False, "rate limited", 429, 0.0, stage="yfinance")

    reset_yahoo_health_cache()
    health = check_yahoo_availability(
        probe=_rate_limited, attempts=3, retry_delay=0.0, force=True
    )

    assert len(calls) == 1  # not three
    assert health.available is False


def test_transient_failures_still_retry(monkeypatch):
    calls = []

    def _flaky(timeout):
        calls.append(timeout)
        return YahooHealth(True, "ok", 200, 0.0, stage="yfinance")

    reset_yahoo_health_cache()
    health = check_yahoo_availability(
        probe=_flaky, attempts=3, retry_delay=0.0, force=True
    )
    assert health.available is True
    assert len(calls) == 1  # first attempt succeeded

    reset_yahoo_health_cache()
    calls.clear()
    health = check_yahoo_availability(
        probe=_flaky, attempts=2, retry_delay=0.0, force=True
    )
    assert health.available is True


def test_preflight_failure_skips_every_per_ticker_request(monkeypatch):
    """A failed preflight must not authorise thousands of doomed fetches."""
    import backend.services.price_service as price_service_module
    from backend.services.price_service import PriceService
    from backend.services.yahoo_health import YahooHealth

    def _boom(*args, **kwargs):
        raise AssertionError("no per-ticker request may happen when preflight failed")

    monkeypatch.setattr(price_service_module.yf, "Ticker", _boom)
    monkeypatch.setattr(price_service_module.time, "sleep", lambda *_: None)

    service = PriceService(
        health_fn=lambda **kwargs: YahooHealth(
            False, "rate limited", 429, 0.0, stage="yfinance"
        )
    )

    assert service.get_market_snapshots(["AAPL", "KO", "MSFT"]) == {}
    assert service.last_health().http_status == 429
