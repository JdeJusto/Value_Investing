"""Unit tests for the Yahoo 429 consecutive-failure watcher.

The watcher exists because a rate limit is a silent failure: the run finishes
and every price column is N/A. These tests pin the streak arithmetic, the
"once per streak" alerting, the marker file lifecycle and the report section.
"""

from __future__ import annotations

import json

from backend.services.yahoo_streak import (
    DEFAULT_THRESHOLD,
    YahooStreakTracker,
    load_alerts_config,
)


def _tracker(tmp_path, threshold: int = 3, enabled: bool = True) -> YahooStreakTracker:
    return YahooStreakTracker(
        state_path=tmp_path / "state" / "streak.json",
        flag_path=tmp_path / "alerts" / "yahoo_429_active.flag",
        threshold=threshold,
        enabled=enabled,
    )


# ----------------------------------------------------------------------
# streak arithmetic
# ----------------------------------------------------------------------


def test_streak_increments_on_consecutive_failures(tmp_path):
    tracker = _tracker(tmp_path)
    for expected in (1, 2, 3, 4):
        update = tracker.record_failure("HTTP 429")
        assert update.consecutive_failures == expected
    assert tracker.load()["consecutive_failures"] == 4


def test_streak_resets_on_success(tmp_path):
    tracker = _tracker(tmp_path)
    tracker.record_failure("HTTP 429")
    tracker.record_failure("HTTP 429")

    update = tracker.record_success()

    assert update.consecutive_failures == 0
    assert update.recovered is True
    state = tracker.load()
    assert state["consecutive_failures"] == 0
    assert state["first_failure_at"] is None
    assert state["last_success_at"] is not None


def test_success_without_a_prior_failure_is_not_a_recovery(tmp_path):
    update = _tracker(tmp_path).record_success()

    assert update.consecutive_failures == 0
    assert update.recovered is False
    assert update.alert_triggered is False


def test_first_failure_at_is_kept_for_the_streak(tmp_path):
    tracker = _tracker(tmp_path)
    first = tracker.record_failure("HTTP 429").state["first_failure_at"]
    tracker.record_failure("HTTP 429")
    assert tracker.load()["first_failure_at"] == first
    assert tracker.load()["last_failure_at"] is not None

    tracker.record_success()
    restarted = tracker.record_failure("HTTP 429")
    assert restarted.state["first_failure_at"] == restarted.state["last_failure_at"]


# ----------------------------------------------------------------------
# alerting
# ----------------------------------------------------------------------


def test_alert_does_not_fire_below_the_threshold(tmp_path):
    tracker = _tracker(tmp_path, threshold=3)
    for expected in (1, 2):
        update = tracker.record_failure("HTTP 429")
        assert expected < 3
        assert update.alert_triggered is False
        assert update.alerted is False
    assert not tracker.flag_path.exists()


def test_alert_fires_once_at_the_threshold(tmp_path):
    tracker = _tracker(tmp_path, threshold=3)
    for _ in range(3):
        update = tracker.record_failure("HTTP 429")
    assert update.alert_triggered is True
    assert update.alerted is True
    assert tracker.flag_path.exists()

    # Further failures keep the streak but do not re-alert
    for _ in range(3):
        again = tracker.record_failure("HTTP 429")
    assert again.alert_triggered is False
    assert again.alerted is True
    assert again.consecutive_failures == 6


def test_recovery_removes_the_flag_and_allows_a_new_alert(tmp_path):
    tracker = _tracker(tmp_path, threshold=2)
    tracker.record_failure("HTTP 429")
    assert tracker.record_failure("HTTP 429").alert_triggered is True
    assert tracker.flag_path.exists()

    tracker.record_success()
    assert not tracker.flag_path.exists()
    assert tracker.load()["alerted"] is False

    # A new streak alerts again from scratch
    tracker.record_failure("HTTP 429")
    assert tracker.record_failure("HTTP 429").alert_triggered is True
    assert tracker.flag_path.exists()


def test_flag_content_carries_the_diagnosis(tmp_path):
    tracker = _tracker(tmp_path, threshold=1)
    tracker.record_failure("Yahoo returned HTTP 429 (rate limited)")
    text = tracker.flag_path.read_text(encoding="utf-8")

    assert "HTTP 429" in text
    assert "first_failure_at" in text
    assert "threshold: 1" in text


def test_report_lines_only_when_alerted(tmp_path):
    tracker = _tracker(tmp_path, threshold=2)
    quiet = tracker.record_failure("HTTP 429")
    assert quiet.report_lines() == []

    loud = tracker.record_failure("HTTP 429")
    text = "\n".join(loud.report_lines())
    assert "2 consecutive runs" in text
    assert "429" in text
    assert "BUY_SIGNAL" in text  # the real impact
    assert "curl" in text  # and a way to check


# ----------------------------------------------------------------------
# persistence
# ----------------------------------------------------------------------


def test_state_survives_a_restart(tmp_path):
    tracker = _tracker(tmp_path, threshold=3)
    tracker.record_failure("HTTP 429")
    tracker.record_failure("HTTP 429")

    fresh = _tracker(tmp_path, threshold=3)
    assert fresh.load()["consecutive_failures"] == 2
    assert fresh.record_failure("HTTP 429").alert_triggered is True


def test_corrupt_state_is_not_fatal(tmp_path):
    tracker = _tracker(tmp_path)
    tracker.state_path.parent.mkdir(parents=True, exist_ok=True)
    tracker.state_path.write_text("{not json", encoding="utf-8")

    assert tracker.load()["consecutive_failures"] == 0
    assert tracker.record_failure("HTTP 429").consecutive_failures == 1


def test_write_is_atomic(tmp_path):
    tracker = _tracker(tmp_path)
    tracker.record_failure("HTTP 429")
    assert not list(tracker.state_path.parent.glob("*.tmp"))
    payload = json.loads(tracker.state_path.read_text())
    assert payload["consecutive_failures"] == 1
    assert "updated_at" in payload


def test_disabled_tracker_writes_nothing(tmp_path):
    tracker = _tracker(tmp_path, enabled=False)
    update = tracker.record_failure("HTTP 429")

    assert update.consecutive_failures == 0
    assert not tracker.state_path.exists()
    assert not tracker.flag_path.exists()


# ----------------------------------------------------------------------
# configuration
# ----------------------------------------------------------------------


def test_threshold_default_and_environment_override(monkeypatch):
    monkeypatch.delenv("YAHOO_429_STREAK_THRESHOLD", raising=False)
    assert load_alerts_config() == DEFAULT_THRESHOLD == 3

    monkeypatch.setenv("YAHOO_429_STREAK_THRESHOLD", "7")
    assert load_alerts_config() == 7

    monkeypatch.setenv("YAHOO_429_STREAK_THRESHOLD", "not-a-number")
    assert load_alerts_config() == DEFAULT_THRESHOLD


def test_threshold_is_read_from_the_config_file(tmp_path, monkeypatch):
    monkeypatch.delenv("YAHOO_429_STREAK_THRESHOLD", raising=False)
    path = tmp_path / "alerts.yaml"
    path.write_text("# comment\nyahoo_429_streak_threshold: 5\n", encoding="utf-8")

    assert load_alerts_config(str(path)) == 5

    path.write_text("yahoo_429_streak_threshold: oops\n", encoding="utf-8")
    assert load_alerts_config(str(path)) == DEFAULT_THRESHOLD


def test_shipped_config_declares_the_threshold():
    """config/alerts.yaml must exist and declare the key the code reads."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    config = root / "config" / "alerts.yaml"
    assert config.exists(), "config/alerts.yaml is missing"
    assert load_alerts_config(str(config)) >= 1


# ----------------------------------------------------------------------
# report rendering
# ----------------------------------------------------------------------


def test_report_renders_the_yahoo_alert_section():
    from datetime import date as _date

    from backend.services.daily_report_service import DailyReport, build_markdown

    state = {
        "consecutive_failures": 4,
        "first_failure_at": "2026-09-25T07:00:00Z",
        "last_failure_at": "2026-09-28T06:00:00Z",
        "last_success_at": "2026-09-24T06:00:00Z",
        "alerted": True,
    }
    body = build_markdown(
        DailyReport(report_date=_date(2026, 9, 28), yahoo_streak=state)
    )

    assert "## ⚠️ Yahoo Rate Limit Alert" in body
    assert "4 consecutive runs" in body
    assert "2026-09-25T07:00:00Z" in body


def test_report_omits_the_section_when_healthy():
    from datetime import date as _date

    from backend.services.daily_report_service import DailyReport, build_markdown

    assert "Yahoo Rate Limit Alert" not in build_markdown(
        DailyReport(report_date=_date(2026, 9, 28))
    )
    assert "Yahoo Rate Limit Alert" not in build_markdown(
        DailyReport(
            report_date=_date(2026, 9, 28),
            yahoo_streak={"consecutive_failures": 1, "alerted": False},
        )
    )


# ----------------------------------------------------------------------
# a failure is not automatically a rate limit
# ----------------------------------------------------------------------


def test_is_rate_limit_distinguishes_causes():
    from backend.services.yahoo_health import YahooHealth
    from backend.services.yahoo_streak import is_rate_limit

    assert is_rate_limit(YahooHealth(False, "Yahoo returned HTTP 429 (rate limited)", 429, 0.0))
    assert is_rate_limit(YahooHealth(False, "HTTP 429", None, 0.0))
    assert is_rate_limit(YahooHealth(False, "Too Many Requests", None, 0.0))
    # A local network problem must not be reported as a rate limit
    assert not is_rate_limit(
        YahooHealth(False, "Yahoo unreachable: Temporary failure in name resolution", None, 0.0)
    )
    assert not is_rate_limit(YahooHealth(False, "Yahoo returned HTTP 500", 500, 0.0))
    assert not is_rate_limit(YahooHealth(True, "ok", 200, 0.0))


def test_non_rate_limit_failure_uses_its_own_wording(tmp_path):
    tracker = _tracker(tmp_path, threshold=2)
    tracker.record_failure("name resolution failed", rate_limited=False)
    update = tracker.record_failure("name resolution failed", rate_limited=False)

    assert update.alert_triggered is True
    assert update.state["rate_limited"] is False
    text = "\n".join(update.report_lines())
    assert "an unrelated failure" in text
    assert "Not a rate limit" in text
    assert "rate_limited: false" in tracker.flag_path.read_text(encoding="utf-8")


def test_rate_limit_failure_keeps_the_rate_limit_wording(tmp_path):
    tracker = _tracker(tmp_path, threshold=1)
    update = tracker.record_failure("HTTP 429 (rate limited)", rate_limited=True)

    assert "HTTP 429 (rate limit)" in "\n".join(update.report_lines())
    assert "rate_limited: true" in tracker.flag_path.read_text(encoding="utf-8")


def test_report_title_reflects_the_cause():
    from datetime import date as _date

    from backend.services.daily_report_service import DailyReport, build_markdown

    base = {
        "consecutive_failures": 3,
        "first_failure_at": "2026-09-25T07:00:00Z",
        "last_failure_at": "2026-09-28T06:00:00Z",
        "alerted": True,
    }
    limited = build_markdown(
        DailyReport(report_date=_date(2026, 9, 28), yahoo_streak={**base, "rate_limited": True})
    )
    other = build_markdown(
        DailyReport(report_date=_date(2026, 9, 28), yahoo_streak={**base, "rate_limited": False})
    )

    assert "## ⚠️ Yahoo Rate Limit Alert" in limited
    assert "## ⚠️ Yahoo Unavailable Alert" in other
