"""Unit tests for the dividend service (Yahoo-sourced, never persisted)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from backend.services.dividend_service import (
    DividendRecord,
    DividendService,
    _parse_dividends,
)


def _series(dates, amounts):
    import pandas as pd

    return pd.Series(amounts, index=pd.to_datetime(dates), dtype=float)


def test_parse_dividends_returns_records_most_recent_first():
    raw = _series(
        [date(2024, 6, 15), date(2023, 6, 15), date(2022, 6, 15)],
        [0.5, 0.4, 0.3],
    )

    records = _parse_dividends(raw)

    assert [r.ex_date for r in records] == [
        date(2024, 6, 15),
        date(2023, 6, 15),
        date(2022, 6, 15),
    ]
    assert [r.amount for r in records] == [0.5, 0.4, 0.3]


def test_parse_dividends_skips_non_positive_and_unparseable():
    import pandas as pd

    raw = pd.Series(
        [0.0, 1.5, -0.2, 2.0],
        index=pd.to_datetime(
            [date(2024, 1, 1), date(2023, 1, 1), date(2022, 1, 1), "not-a-date"],
            errors="coerce",
        ),
    )

    records = _parse_dividends(raw)

    assert [r.amount for r in records] == [1.5]  # 0.0, -0.2 and NaT skipped


def test_consecutive_years_counts_the_current_unbroken_run():
    raw = _series(
        [date(2024, 6, 15), date(2023, 6, 15), date(2022, 6, 15)]
        + [date(2000, 6, 15), date(1999, 6, 15)],
        [0.5, 0.4, 0.3, 0.1, 0.1],
    )
    service = DividendService(
        yf_ticker=lambda t: type("T", (), {"dividends": raw})(), health_fn=lambda: True
    )

    assert service.consecutive_years("AAPL") == 3


def test_consecutive_years_returns_zero_without_dividends():
    import pandas as pd

    service = DividendService(
        yf_ticker=lambda t: type("T", (), {"dividends": pd.Series(dtype=float)})(),
        health_fn=lambda: True,
    )

    assert service.consecutive_years("AAPL") == 0
    assert service.has_dividend_history("AAPL") is False


def test_has_dividend_history_uses_the_threshold():
    raw = _series([date(2024, 6, 15), date(2023, 6, 15)], [0.5, 0.4])
    service = DividendService(
        yf_ticker=lambda t: type("T", (), {"dividends": raw})(), health_fn=lambda: True
    )

    assert service.has_dividend_history("AAPL", min_years=2) is True
    assert service.has_dividend_history("AAPL", min_years=3) is False


def test_preflight_failure_means_no_fetch(monkeypatch):
    def _boom(ticker):
        raise AssertionError("no HTTP call may happen when preflight failed")

    service = DividendService(yf_ticker=_boom, health_fn=lambda: False)

    assert service.get_dividends("AAPL") == []
    assert service.consecutive_years("AAPL") == 0


def test_cache_avoids_a_second_fetch(monkeypatch):
    calls = {"n": 0}
    raw = _series([date(2024, 6, 15)], [0.5])

    def _factory(ticker):
        calls["n"] += 1
        return type("T", (), {"dividends": raw})()

    service = DividendService(yf_ticker=_factory, health_fn=lambda: True)

    service.get_dividends("AAPL")
    service.get_dividends("AAPL")

    assert calls["n"] == 1


def test_records_are_immutable():
    record = DividendRecord(ex_date=date(2024, 6, 15), amount=0.5)
    with pytest.raises(FrozenInstanceError):
        record.amount = 1.0  # type: ignore[misc]
