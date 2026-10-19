"""The workflow's SEC/Yahoo probes are retried through the shared helper.

``assert_*`` naming keeps pytest from collecting the local helpers below.
"""

from __future__ import annotations

import pytest

from backend.services.sec_health import SecHealth
from backend.services.yahoo_health import YahooHealth
from scripts import daily_workflow


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(daily_workflow, "_retry_sleep", lambda _delay: None)


def test_probe_sec_retries_transient_failures_then_succeeds(monkeypatch):
    calls = {"count": 0}

    def flaky(*, timeout, attempts):
        calls["count"] += 1
        if calls["count"] < 3:
            # A transient verdict carries no HTTP status.
            return SecHealth(False, "SEC unreachable: timed out", None, 0.0)
        return SecHealth(True, "ok", 200, 0.0)

    monkeypatch.setattr(daily_workflow, "check_sec_availability", flaky)

    assert daily_workflow._probe_sec() is True
    assert calls["count"] == 3  # two transient failures absorbed, no more


def test_probe_sec_gives_up_after_the_attempt_budget(monkeypatch):
    calls = {"count": 0}

    def always_down(*, timeout, attempts):
        calls["count"] += 1
        return SecHealth(False, "SEC unreachable: timed out", None, 0.0)

    monkeypatch.setattr(daily_workflow, "check_sec_availability", always_down)

    with pytest.raises(ConnectionError):
        daily_workflow._probe_sec()
    assert calls["count"] == 3


def test_probe_sec_does_not_retry_a_non_transient_verdict(monkeypatch):
    calls = {"count": 0}

    def rate_limited(*, timeout, attempts):
        calls["count"] += 1
        return SecHealth(False, "SEC returned HTTP 403", 403, 0.0)

    monkeypatch.setattr(daily_workflow, "check_sec_availability", rate_limited)

    assert daily_workflow._probe_sec() is False
    assert calls["count"] == 1  # 403 is final; retrying makes it worse


def test_probe_yahoo_retries_transient_failures_then_succeeds(monkeypatch):
    calls = {"count": 0}

    def flaky(*, timeout, attempts):
        calls["count"] += 1
        if calls["count"] < 2:
            return YahooHealth(False, "Yahoo unreachable: timed out", None, 0.0)
        return YahooHealth(True, "ok", 200, 0.0)

    monkeypatch.setattr(daily_workflow, "check_yahoo_availability", flaky)

    assert daily_workflow._probe_yahoo() is True
    assert calls["count"] == 2


def test_probe_yahoo_does_not_retry_a_rate_limit(monkeypatch):
    calls = {"count": 0}

    def rate_limited(*, timeout, attempts):
        calls["count"] += 1
        return YahooHealth(False, "Yahoo returned HTTP 429", 429, 0.0)

    monkeypatch.setattr(daily_workflow, "check_yahoo_availability", rate_limited)

    assert daily_workflow._probe_yahoo() is False
    assert calls["count"] == 1


def test_probe_sec_passes_the_short_timeout(monkeypatch):
    seen = {}

    def record(*, timeout, attempts):
        seen["timeout"] = timeout
        seen["attempts"] = attempts
        return SecHealth(True, "ok", 200, 0.0)

    monkeypatch.setattr(daily_workflow, "check_sec_availability", record)

    assert daily_workflow._probe_sec() is True
    # One attempt at the probe level: the retry policy lives in the shared
    # helper (with_retry), not doubled up inside the preflight.
    assert seen == {"timeout": daily_workflow.HEALTH_CHECK_TIMEOUT_S, "attempts": 1}
