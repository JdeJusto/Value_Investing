"""Tests for the async retry helper."""

from __future__ import annotations

import asyncio

import pytest

from backend.services._retry import retry_async


def _recording_sleep(monkeypatch) -> list[float]:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return delays


def test_retry_succeeds_after_transient_failures(monkeypatch):
    delays = _recording_sleep(monkeypatch)
    calls = {"count": 0}

    async def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise ConnectionError("transient")
        return "ok"

    assert asyncio.run(retry_async(flaky, attempts=3, base_delay=0.5)) == "ok"
    assert calls["count"] == 3
    assert delays == [0.5, 1.0]


def test_retry_gives_up_after_attempts(monkeypatch):
    delays = _recording_sleep(monkeypatch)
    calls = {"count": 0}

    async def always_fail():
        calls["count"] += 1
        raise TimeoutError("still down")

    with pytest.raises(TimeoutError):
        asyncio.run(retry_async(always_fail, attempts=3, base_delay=0.5))
    assert calls["count"] == 3
    assert delays == [0.5, 1.0]


def test_retry_does_not_retry_non_network_errors(monkeypatch):
    delays = _recording_sleep(monkeypatch)
    calls = {"count": 0}

    async def bad_value():
        calls["count"] += 1
        raise ValueError("bug, not a network blip")

    with pytest.raises(ValueError):
        asyncio.run(retry_async(bad_value, attempts=3, base_delay=0.5))
    assert calls["count"] == 1
    assert delays == []


def test_retry_caps_the_delay(monkeypatch):
    delays = _recording_sleep(monkeypatch)

    async def always_fail():
        raise ConnectionError("nope")

    with pytest.raises(ConnectionError):
        asyncio.run(
            retry_async(always_fail, attempts=3, base_delay=10.0, max_delay=4.0)
        )
    assert delays == [4.0, 4.0]


def test_retry_rejects_a_non_positive_attempt_count():
    async def noop():
        return None

    with pytest.raises(ValueError):
        asyncio.run(retry_async(noop, attempts=0))
