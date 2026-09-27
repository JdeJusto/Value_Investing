"""Unit tests for the three report fixes (2026-09-28 session).

1. prices_mode must describe what actually happened, not what was requested.
2. Alert ordering must be deterministic across runs and worker counts.
3. The default Yahoo probe User-Agent must be the minimal one.
"""

from __future__ import annotations

from datetime import date as _date

import pytest

from backend.alerts.alert_engine import Alert
from backend.services.alerts_cache import alert_sort_key, sorted_alerts
from backend.services.daily_report_service import DailyReport, build_markdown
from backend.services.yahoo_health import YahooHealth
from scripts.daily_workflow import _prices_mode, sort_alerts


# ----------------------------------------------------------------------
# Fix 1.2 — prices_mode
# ----------------------------------------------------------------------


class _Args:
    def __init__(self, no_prices: bool = False):
        self.no_prices = no_prices


class _Service:
    def __init__(self, health=None):
        self._health = health

    def last_health(self):
        return self._health


def test_prices_mode_real_time_when_quotes_were_fetched():
    mode = _prices_mode(
        _Args(),
        _Service(YahooHealth(True, "ok", 200, 0.0)),
        {"snapshots": {"AAPL": {"regularMarketPrice": 100.0}}},
    )
    assert mode == "real-time"


def test_prices_mode_unavailable_when_the_preflight_failed():
    """The header must not claim real-time data it never got."""
    mode = _prices_mode(
        _Args(),
        _Service(YahooHealth(False, "Yahoo returned HTTP 429", 429, 0.0)),
        {"snapshots": {}},
    )
    assert mode == "unavailable"


def test_prices_mode_unavailable_when_nothing_came_back_despite_a_good_probe():
    mode = _prices_mode(
        _Args(),
        _Service(YahooHealth(True, "ok", 200, 0.0)),
        {"snapshots": {}},
    )
    assert mode == "unavailable"


def test_prices_mode_no_prices_when_not_requested():
    mode = _prices_mode(
        _Args(no_prices=True),
        _Service(YahooHealth(True, "ok", 200, 0.0)),
        {"snapshots": {"AAPL": {}}},
    )
    assert mode == "no-prices"


def test_report_header_matches_the_mode():
    def _body(mode: str) -> str:
        return build_markdown(
            DailyReport(report_date=_date(2026, 9, 28), prices_mode=mode)
        )

    assert "prices: **real-time**" in _body("real-time")
    assert "prices: **unavailable**" in _body("unavailable")
    assert "prices: **no-prices**" in _body("no-prices")

    # The "never persisted" guarantee is stated for every mode that touched
    # prices, and the unavailability is explained.
    assert "no price is ever persisted" in _body("real-time")
    assert "no price is ever persisted" in _body("unavailable")
    assert "no price is ever persisted" not in _body("no-prices")
    assert "were **not** available" in _body("unavailable")
    assert "were **not** available" not in _body("real-time")


def test_unavailable_header_does_not_contradict_the_price_stage_section():
    body = build_markdown(
        DailyReport(
            report_date=_date(2026, 9, 28),
            prices_mode="unavailable",
            prices_stage={"processed": 2528, "failures": {"no_yahoo": 2528}},
        )
    )
    assert "prices: **unavailable**" in body
    assert "no_yahoo: 2528" in body


# ----------------------------------------------------------------------
# Fix 1.3 — deterministic alert ordering
# ----------------------------------------------------------------------


def _alert(ticker: str, kind: str, reason: str = "r") -> Alert:
    return Alert(ticker=ticker, alert_type=kind, reason=[reason], confidence="MEDIUM")


def test_sort_alerts_is_deterministic_whatever_the_input_order():
    items = [
        _alert("ZZZ", "TRIGGER_EVENT"),
        _alert("AAA", "TRIGGER_EVENT"),
        _alert("MMM", "BUY_SIGNAL"),
        _alert("AAA", "BUY_SIGNAL"),
    ]
    expected = [("AAA", "BUY_SIGNAL"), ("AAA", "TRIGGER_EVENT"),
                ("MMM", "BUY_SIGNAL"), ("ZZZ", "TRIGGER_EVENT")]

    import itertools

    # Every permutation yields the same order.
    for permutation in itertools.permutations(items):
        got = [(a.ticker, a.alert_type) for a in sort_alerts(list(permutation))]
        assert got == expected


def test_sort_alerts_uses_the_first_reason_as_tiebreaker():
    items = [
        _alert("AAA", "TRIGGER_EVENT", "trigger z"),
        _alert("AAA", "TRIGGER_EVENT", "trigger a"),
    ]
    ordered = sort_alerts(items)
    assert [a.reason[0] for a in ordered] == ["trigger a", "trigger z"]


def test_sort_alerts_tolerates_alerts_without_reason():
    assert sort_alerts([Alert(ticker="A", alert_type="T", reason=[], confidence="C")])
    assert sort_alerts([Alert(ticker="A", alert_type="T", reason=None, confidence="C")])


def test_alert_sort_key_works_on_dicts_and_objects():
    obj = _alert("BBB", "TRIGGER_EVENT")
    as_dict = {"ticker": "BBB", "alert_type": "TRIGGER_EVENT", "reason": ["r"]}
    assert alert_sort_key(obj) == alert_sort_key(as_dict) == ("BBB", "TRIGGER_EVENT", "r")


def test_cache_stores_alerts_in_the_canonical_order(tmp_path):
    from backend.services.alerts_cache import AlertsCache

    cache = AlertsCache(directory=tmp_path)
    items = [
        _alert("ZZZ", "TRIGGER_EVENT"),
        _alert("AAA", "BUY_SIGNAL"),
        _alert("AAA", "TRIGGER_EVENT"),
    ]

    def _as_dict(alert):
        return {
            "ticker": alert.ticker,
            "alert_type": alert.alert_type,
            "reason": list(alert.reason),
            "confidence": alert.confidence,
        }

    cache.put(_date(2026, 9, 28), "run-1", "d", items, as_dict=_as_dict)
    stored = cache.get(_date(2026, 9, 28), "run-1", "d")

    assert [(a["ticker"], a["alert_type"]) for a in stored] == [
        ("AAA", "BUY_SIGNAL"),
        ("AAA", "TRIGGER_EVENT"),
        ("ZZZ", "TRIGGER_EVENT"),
    ]


def test_sorted_alerts_helper_is_a_no_op_on_sorted_input():
    items = [_alert("AAA", "TRIGGER_EVENT"), _alert("BBB", "BUY_SIGNAL")]
    assert [a.ticker for a in sorted_alerts(items)] == ["AAA", "BBB"]


def test_two_different_worker_orders_render_identical_alert_sections():
    """The parallelism may vary; the report must not."""
    from backend.alerts.alert_engine import dedupe

    batch = [
        _alert("AAPL", "TRIGGER_EVENT", "trigger a"),
        _alert("KO", "BUY_SIGNAL", "rank 80"),
        _alert("MSFT", "TRIGGER_EVENT", "trigger b"),
        _alert("AAPL", "BUY_SIGNAL", "rank 85"),
    ]
    first = sort_alerts(dedupe(list(batch)))
    shuffled = sort_alerts(dedupe([batch[2], batch[0], batch[3], batch[1]]))

    def _section(alerts):
        return build_markdown(
            DailyReport(report_date=_date(2026, 9, 28), alerts=[
                {"ticker": a.ticker, "alert_type": a.alert_type,
                 "reason": a.reason, "confidence": a.confidence}
                for a in alerts
            ])
        ).split("## Alerts")[1]

    assert _section(first) == _section(shuffled)


# ----------------------------------------------------------------------
# Fix 1.1 — default User-Agent
# ----------------------------------------------------------------------


def test_default_user_agent_is_minimal():
    from backend.services.yahoo_health import DEFAULT_USER_AGENT

    assert DEFAULT_USER_AGENT == "Mozilla/5.0"


def test_price_service_does_not_send_its_own_user_agent():
    """yfinance manages its own agent; the preflight is the only one we set."""
    import inspect

    from backend.services import price_service

    source = inspect.getsource(price_service)
    assert "User-Agent" not in source
