"""Unit tests for the SEC availability preflight (hermetic, no network)."""

from __future__ import annotations

import time

import pytest

from backend.services.sec_health import (
    SEC_HEALTH_URL,
    SecHealth,
    check_sec_availability,
    reset_sec_health_cache,
)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    reset_sec_health_cache()
    monkeypatch.setenv("SEC_USER_AGENT", "Tests/1.0 test@example.com")
    yield
    reset_sec_health_cache()


def _ok(url, user_agent, timeout):
    return SecHealth(True, "ok", 200, 0.0)


def _down(reason, status=None):
    def probe(url, user_agent, timeout):
        return SecHealth(False, reason, status, 0.0)

    return probe


def test_missing_user_agent_is_unavailable_without_http(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    calls = []

    def probe(*args):
        calls.append(args)
        return _ok(*args)

    health = check_sec_availability(probe=probe)
    assert health.available is False
    assert "SEC_USER_AGENT" in health.reason
    assert calls == []  # no request attempted without a compliant UA


def test_ok_probe_is_available():
    health = check_sec_availability(probe=_ok)
    assert health.available is True
    assert health.http_status == 200
    assert health.reason == "ok"


def test_403_reports_rate_limit_reason():
    health = check_sec_availability(
        probe=_down("SEC returned HTTP 403 (rate limit)", 403), retry_delay=0.0
    )
    assert health.available is False
    assert health.http_status == 403
    assert "403" in health.reason


def test_transport_error_is_unavailable_and_retried_once():
    calls = []

    def probe(url, user_agent, timeout):
        calls.append(1)
        return SecHealth(False, "SEC unreachable: timed out", None, 0.0)

    health = check_sec_availability(probe=probe, retry_delay=0.0)
    assert health.available is False
    assert len(calls) == 2  # one retry absorbs intermittent failures


def test_intermittent_failure_recovers_on_retry():
    calls = []

    def probe(url, user_agent, timeout):
        calls.append(1)
        if len(calls) == 1:
            return SecHealth(False, "SEC unreachable: transient", None, 0.0)
        return SecHealth(True, "ok", 200, 0.0)

    health = check_sec_availability(probe=probe, retry_delay=0.0)
    assert health.available is True
    assert len(calls) == 2


def test_result_is_cached_within_ttl_and_force_bypasses():
    calls = []

    def probe(url, user_agent, timeout):
        calls.append(1)
        return SecHealth(True, "ok", 200, 0.0)

    first = check_sec_availability(probe=probe, ttl=60)
    second = check_sec_availability(probe=probe, ttl=60)
    assert calls == [1]  # second call served from cache
    assert second == first

    check_sec_availability(probe=probe, ttl=60, force=True)
    assert calls == [1, 1]


def test_expired_ttl_reprobes():
    calls = []

    def probe(url, user_agent, timeout):
        calls.append(1)
        return SecHealth(True, "ok", 200, 0.0)

    check_sec_availability(probe=probe, ttl=0)
    time.sleep(0.01)
    check_sec_availability(probe=probe, ttl=0)
    assert len(calls) == 2


def test_probe_uses_the_production_probe_by_default(monkeypatch):
    """Without an injected probe the module probe is used (and mocked here)."""
    from backend.services import sec_health

    seen = {}

    def fake_probe(url, user_agent, timeout):
        seen["url"] = url
        seen["ua"] = user_agent
        return SecHealth(True, "ok", 200, 0.0)

    monkeypatch.setattr(sec_health, "_probe", fake_probe)
    health = check_sec_availability()
    assert health.available is True
    assert seen["url"] == SEC_HEALTH_URL
    assert seen["ua"] == "Tests/1.0 test@example.com"
