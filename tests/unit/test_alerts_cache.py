"""Unit tests for the per-day alerts cache.

The cache replays the WHOLE alert list (the engine calibrates trigger floors
cross-sectionally, so a per-ticker cache would change which triggers fire) and
is keyed by day + run id + a digest of the alert inputs.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend.alerts.alert_engine import Alert
from backend.services.alerts_cache import AlertsCache, input_digest


def _alert(ticker: str, kind: str = "TRIGGER_EVENT") -> Alert:
    return Alert(
        ticker=ticker,
        alert_type=kind,
        reason=[f"trigger {kind.lower()}"],
        confidence="MEDIUM",
    )


def _analysis(score=70.0, buffett=60.0, deltas=None, confidence="HIGH"):
    return {
        "composite_score": {"total_score": score, "confidence": confidence},
        "buffett_score": buffett,
        "opportunity": None,
        "delta_metrics": deltas or {},
    }


def _as_dict(alert):
    return {
        "ticker": alert.ticker,
        "alert_type": alert.alert_type,
        "reason": list(alert.reason),
        "confidence": alert.confidence,
    }


def test_cache_hit_returns_the_same_alerts(tmp_path):
    cache = AlertsCache(directory=tmp_path)
    day = date(2026, 9, 27)
    alerts = [_alert("AAPL"), _alert("KO", "BUY_SIGNAL")]

    cache.put(day, "run-1", "digest-1", alerts, as_dict=_as_dict)
    got = cache.get(day, "run-1", "digest-1")

    assert got is not None
    assert [item["ticker"] for item in got] == ["AAPL", "KO"]
    assert got[1]["alert_type"] == "BUY_SIGNAL"
    assert cache.hits == 1


def test_different_run_id_triggers_recomputation(tmp_path):
    cache = AlertsCache(directory=tmp_path)
    day = date(2026, 9, 27)
    cache.put(day, "run-1", "digest-1", [_alert("AAPL")], as_dict=_as_dict)

    assert cache.get(day, "run-2", "digest-1") is None
    assert cache.get(day, "run-1", "digest-1") is not None
    assert cache.misses == 1
    assert cache.hits == 1


def test_different_date_triggers_recomputation(tmp_path):
    cache = AlertsCache(directory=tmp_path)
    cache.put(
        date(2026, 9, 27), "run-1", "digest-1", [_alert("AAPL")], as_dict=_as_dict
    )

    assert cache.get(date(2026, 9, 28), "run-1", "digest-1") is None
    # each day gets its own file
    assert cache.path_for(date(2026, 9, 28)).name == "alerts_2026-09-28.json"


def test_different_digest_triggers_recomputation(tmp_path):
    """New facts change the scores, so the digest must change with them."""
    cache = AlertsCache(directory=tmp_path)
    day = date(2026, 9, 27)
    cache.put(day, "run-1", "digest-1", [_alert("AAPL")], as_dict=_as_dict)

    assert cache.get(day, "run-1", "digest-2") is None


def test_disabled_cache_is_a_noop(tmp_path):
    cache = AlertsCache(directory=tmp_path, enabled=False)
    cache.put(date(2026, 9, 27), "run-1", "d", [_alert("AAPL")], as_dict=_as_dict)

    assert cache.get(date(2026, 9, 27), "run-1", "d") is None
    assert not (tmp_path / "alerts_2026-09-27.json").exists()


def test_corrupt_entry_is_a_miss(tmp_path):
    cache = AlertsCache(directory=tmp_path)
    day = date(2026, 9, 27)
    cache.put(day, "run-1", "d", [_alert("AAPL")], as_dict=_as_dict)
    cache.path_for(day).write_text("{not json", encoding="utf-8")

    assert cache.get(day, "run-1", "d") is None
    assert cache.misses == 1


def test_write_is_atomic(tmp_path):
    cache = AlertsCache(directory=tmp_path)
    cache.put(date(2026, 9, 27), "run-1", "d", [_alert("AAPL")], as_dict=_as_dict)

    assert not list(tmp_path.glob("*.tmp"))
    payload = json.loads((tmp_path / "alerts_2026-09-27.json").read_text())
    assert payload["run_id"] == "run-1"
    assert payload["digest"] == "d"
    assert payload["alerts"][0]["ticker"] == "AAPL"
    assert "computed_at" in payload


def test_version_bump_invalidates(tmp_path):
    old = AlertsCache(directory=tmp_path, version="1")
    old.put(date(2026, 9, 27), "run-1", "d", [_alert("AAPL")], as_dict=_as_dict)

    assert (
        AlertsCache(directory=tmp_path, version="2").get(
            date(2026, 9, 27), "run-1", "d"
        )
        is None
    )


# ----------------------------------------------------------------------
# the digest
# ----------------------------------------------------------------------


def test_digest_is_stable_and_order_independent():
    a = {"KO": _analysis(), "AAPL": _analysis(score=80.0)}
    b = {"AAPL": _analysis(score=80.0), "KO": _analysis()}

    assert input_digest(a) == input_digest(b)


@pytest.mark.parametrize(
    "changed",
    [
        {"AAPL": _analysis(score=71.0)},
        {"AAPL": _analysis(buffett=61.0)},
        {"AAPL": _analysis(confidence="LOW")},
        {"AAPL": _analysis(deltas={"gross_margin_delta": 0.05})},
    ],
)
def test_digest_reacts_to_every_input_the_engine_reads(changed):
    base = {"AAPL": _analysis()}

    assert input_digest(base) != input_digest(changed)


def test_digest_reacts_to_the_previous_state():
    """SELL_WARNING compares against the previous day, so it is an input."""
    current = {"AAPL": _analysis()}

    assert input_digest(
        current, {"AAPL": {"composite_score": {"total_score": 60}}}
    ) != (input_digest(current, {"AAPL": {"composite_score": {"total_score": 50}}}))


def test_digest_ignores_tickers_without_an_analysis():
    assert input_digest({"AAPL": None}) == input_digest({"AAPL": None})


def test_digest_is_cheaper_than_serializing_the_whole_analysis():
    """The projection must stay well under the evaluation cost."""
    import json
    import time

    analyses = {
        f"T{i}": {
            **_analysis(score=50.0 + i, deltas={"gross_margin_delta": 0.01 * i}),
            "noise": {f"field_{j}": j for j in range(60)},
        }
        for i in range(500)
    }
    t0 = time.time()
    input_digest(analyses)
    digest_ms = (time.time() - t0) * 1000

    t0 = time.time()
    json.dumps(analyses, sort_keys=True, default=str)
    full_ms = (time.time() - t0) * 1000

    assert digest_ms < full_ms
