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
    """The UA decided the 429 outcome, so it must not be hardcoded-only."""
    from backend.services.yahoo_health import DEFAULT_USER_AGENT, _probe

    seen: dict = {}

    class _Response:
        status = 200

        def read(self, _n):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        seen["ua"] = request.get_header("User-agent")
        return _Response()

    monkeypatch.setattr("backend.services.yahoo_health.urllib.request.urlopen", fake_urlopen)

    _probe(YAHOO_HEALTH_URL, 5.0)
    assert seen["ua"] == DEFAULT_USER_AGENT == "Mozilla/5.0"

    monkeypatch.setenv("YAHOO_HEALTH_USER_AGENT", "Mozilla/5.0")
    _probe(YAHOO_HEALTH_URL, 5.0)
    assert seen["ua"] == "Mozilla/5.0"


def test_default_user_agent_is_the_minimal_one():
    """Regression guard: the full-Chrome UA is what Yahoo answered 429 to."""
    from backend.services.yahoo_health import DEFAULT_USER_AGENT

    assert DEFAULT_USER_AGENT == "Mozilla/5.0"
    # A browser-like agent with no cookie/crumb is what got blocked.
    assert "Chrome" not in DEFAULT_USER_AGENT
    assert "AppleWebKit" not in DEFAULT_USER_AGENT
