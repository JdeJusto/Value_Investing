"""Unit tests for the price-stage fast abort on non-transient failures.

A 429 (rate limit) or 401 (invalid crumb) is answered identically forever:
retrying it burns three attempts and three seconds of backoff per ticker and
turns one refusal into thousands. These tests pin that those two abort
immediately, that a streak of them stops the whole stage, and that transient
failures keep retrying.
"""

from __future__ import annotations

import pytest

from backend.services.price_service import (
    ABORT_REASON_401,
    ABORT_REASON_429,
    PriceService,
    PriceStageAbort,
    classify_fetch_exception,
)


class _RateLimit(Exception):
    """Stand-in for yfinance.exceptions.YFRateLimitError."""


_RateLimit.__name__ = "YFRateLimitError"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("backend.services.price_service.time.sleep", lambda *_: None)


# ----------------------------------------------------------------------
# classification
# ----------------------------------------------------------------------


def test_rate_limit_is_non_transient():
    non_transient, status, reason = classify_fetch_exception(
        _RateLimit("Too Many Requests. Rate limited. Try after a while.")
    )
    assert non_transient is True
    assert status == 429
    assert "rate limited" in reason


def test_invalid_crumb_is_non_transient():
    non_transient, status, _ = classify_fetch_exception(RuntimeError("Invalid Crumb"))
    assert non_transient is True
    assert status == 401


def test_401_in_the_message_is_non_transient():
    non_transient, status, _ = classify_fetch_exception(
        RuntimeError("HTTP Error 401: Unauthorized")
    )
    assert non_transient is True
    assert status == 401


@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError("timed out"),
        ConnectionError("Temporary failure in name resolution"),
        RuntimeError("HTTP Error 503: Service Unavailable"),
        OSError("connection reset by peer"),
    ],
)
def test_transient_errors_keep_retrying(exc):
    non_transient, status, _ = classify_fetch_exception(exc)
    assert non_transient is False
    assert status is None


# ----------------------------------------------------------------------
# per-ticker behaviour
# ----------------------------------------------------------------------


def test_429_aborts_the_ticker_after_one_attempt(monkeypatch):
    attempts = {"n": 0}

    class _Ticker:
        def __init__(self, symbol):
            attempts["n"] += 1

        @property
        def info(self):
            raise _RateLimit("Too Many Requests")

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _Ticker)
    service = PriceService(abort_after=0)

    assert service._fetch_market_snapshot("AAPL") is None
    assert attempts["n"] == 1  # not three


def test_401_aborts_the_ticker_after_one_attempt(monkeypatch):
    attempts = {"n": 0}

    class _Ticker:
        def __init__(self, symbol):
            attempts["n"] += 1

        @property
        def info(self):
            raise RuntimeError("Invalid Crumb")

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _Ticker)
    service = PriceService(abort_after=0)

    assert service._fetch_market_snapshot("AAPL") is None
    assert attempts["n"] == 1


def test_transient_failure_still_retries_three_times(monkeypatch):
    attempts = {"n": 0}

    class _Ticker:
        def __init__(self, symbol):
            attempts["n"] += 1

        @property
        def info(self):
            raise TimeoutError("timed out")

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _Ticker)
    service = PriceService(abort_after=0)

    assert service._fetch_market_snapshot("AAPL") is None
    assert attempts["n"] == 3


def test_successful_fetch_resets_the_streak(monkeypatch):
    state = {"rate_limited": True}

    class _Ticker:
        def __init__(self, symbol):
            pass

        @property
        def info(self):
            if state["rate_limited"]:
                raise _RateLimit("Too Many Requests")
            return {"regularMarketPrice": 100.0}

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _Ticker)
    service = PriceService(abort_after=3)

    service._fetch_market_snapshot("AAPL")
    service._fetch_market_snapshot("KO")
    assert service._abort_streak == 2

    state["rate_limited"] = False
    service._fetch_market_snapshot("MSFT")
    assert service._abort_streak == 0


# ----------------------------------------------------------------------
# stage-level abort
# ----------------------------------------------------------------------


def test_three_consecutive_429s_abort_the_stage(monkeypatch):
    class _Ticker:
        def __init__(self, symbol):
            pass

        @property
        def info(self):
            raise _RateLimit("Too Many Requests")

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _Ticker)
    service = PriceService(abort_after=3)

    with pytest.raises(PriceStageAbort) as excinfo:
        service._fetch_market_snapshot("AAPL")
        service._fetch_market_snapshot("KO")
        service._fetch_market_snapshot("MSFT")

    assert excinfo.value.reason == ABORT_REASON_429
    assert excinfo.value.after == 3


def test_the_stage_stops_and_records_the_abort(monkeypatch):
    """get_market_snapshots returns what it got and records why it stopped."""

    class _Ticker:
        def __init__(self, symbol):
            pass

        @property
        def info(self):
            raise _RateLimit("Too Many Requests")

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _Ticker)
    service = PriceService(abort_after=2)

    snapshots = service.get_market_snapshots(
        ["AAPL", "KO", "MSFT", "WMT", "XOM"], batch_size=5, delay=0, workers=1
    )

    status = service.price_stage_status()
    assert status["status"] == "aborted"
    assert status["aborted_reason"] == ABORT_REASON_429
    assert status["aborted_after"] == 2
    # Only the first ticker completed; the one that tripped the threshold
    # raised before being recorded, and the rest of the universe was never
    # attempted (which is the point: no 2 528 doomed requests).
    assert len(snapshots) == 1
    assert list(snapshots) == ["AAPL"]


def test_a_single_429_does_not_abort_the_stage(monkeypatch):
    """One bad symbol is not a provider outage."""

    class _Ticker:
        def __init__(self, symbol):
            self.symbol = symbol

        @property
        def info(self):
            if self.symbol == "KO":
                raise _RateLimit("Too Many Requests")
            return {"regularMarketPrice": 10.0}

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _Ticker)
    service = PriceService(abort_after=3)

    snapshots = service.get_market_snapshots(["AAPL", "KO", "MSFT"], delay=0, workers=1)

    assert service.price_stage_status()["status"] == "ok"
    assert snapshots["AAPL"] is not None
    assert snapshots["KO"] is None


def test_401_streak_records_the_401_reason(monkeypatch):
    class _Ticker:
        def __init__(self, symbol):
            pass

        @property
        def info(self):
            raise RuntimeError("Invalid Crumb")

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _Ticker)
    service = PriceService(abort_after=2)

    service.get_market_snapshots(["AAPL", "KO", "MSFT"], delay=0, workers=1)

    status = service.price_stage_status()
    assert status["aborted_reason"] == ABORT_REASON_401


def test_abort_disabled_keeps_the_old_behaviour(monkeypatch):
    attempts = {"n": 0}

    class _Ticker:
        def __init__(self, symbol):
            attempts["n"] += 1

        @property
        def info(self):
            raise _RateLimit("Too Many Requests")

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _Ticker)
    service = PriceService()  # abort_after defaults to 0 (disabled)

    for ticker in ("AAPL", "KO", "MSFT", "WMT", "XOM"):
        service._fetch_market_snapshot(ticker)

    assert attempts["n"] == 5  # one attempt each, no stage abort
    assert service.price_stage_status()["status"] == "ok"


def test_successful_run_is_unaffected(monkeypatch):
    class _Ticker:
        def __init__(self, symbol):
            pass

        @property
        def info(self):
            return {"regularMarketPrice": 42.0, "sharesOutstanding": 100}

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _Ticker)
    service = PriceService(abort_after=3)

    snapshots = service.get_market_snapshots(["AAPL", "KO"], delay=0, workers=1)

    assert snapshots["AAPL"]["regularMarketPrice"] == 42.0
    assert service.price_stage_status() == {
        "status": "ok",
        "aborted_reason": None,
        "aborted_after": 0,
    }
    # the derived cache entries are still warmed
    assert service.get_current_price("AAPL") == 42.0


# ----------------------------------------------------------------------
# configuration and reporting
# ----------------------------------------------------------------------


def test_threshold_comes_from_the_config_file(tmp_path, monkeypatch):
    from backend.services.refresh_service import load_refresh_config

    path = tmp_path / "refresh.yaml"
    path.write_text(
        "refresh_workers: 2\nprice_abort_after_consecutive_non_transient: 7\n",
        encoding="utf-8",
    )
    config = load_refresh_config(str(path))
    assert config.price_abort_after_consecutive_non_transient == 7

    monkeypatch.setenv("PRICE_ABORT_AFTER", "5")
    assert (
        load_refresh_config(str(path)).price_abort_after_consecutive_non_transient == 5
    )


def test_shipped_config_sets_the_threshold():
    from pathlib import Path

    from backend.services.refresh_service import load_refresh_config

    root = Path(__file__).resolve().parents[2]
    config_path = root / "config" / "refresh.yaml"
    assert config_path.exists()
    assert (
        load_refresh_config(
            str(config_path)
        ).price_abort_after_consecutive_non_transient
        == 3
    )


def test_configure_sets_the_threshold():
    service = PriceService().configure(abort_after=4)
    assert service.abort_after == 4
    assert service.configure(abort_after=-1).abort_after == 0


def test_report_renders_the_abort_line():
    from datetime import date as _date

    from backend.services.daily_report_service import DailyReport, build_markdown

    body = build_markdown(
        DailyReport(
            report_date=_date(2026, 9, 28),
            prices_mode="unavailable",
            price_stage={
                "status": "aborted",
                "aborted_reason": "yahoo_429",
                "aborted_after": 42,
            },
        )
    )
    assert "Price stage aborted after 42 tickers due to Yahoo 429" in body
    assert "not transient" in body


def test_report_omits_the_line_when_the_stage_is_ok():
    from datetime import date as _date

    from backend.services.daily_report_service import DailyReport, build_markdown

    body = build_markdown(
        DailyReport(report_date=_date(2026, 9, 28), price_stage={"status": "ok"})
    )
    assert "Price stage aborted" not in body


def test_run_state_records_the_abort(tmp_path):
    from backend.services.run_state import RUN_STATE_FILENAME, RunState

    state = RunState.create(
        tmp_path / RUN_STATE_FILENAME,
        universe_spec="all",
        options={},
        total_tickers=100,
    )
    state.set_price_stage_status("aborted", "yahoo_429", 42)

    reloaded = RunState.load(tmp_path / RUN_STATE_FILENAME)
    assert reloaded.price_stage_status() == {
        "status": "aborted",
        "aborted_reason": "yahoo_429",
        "aborted_after": 42,
    }


def test_old_run_state_reads_as_ok(tmp_path):
    import json

    from backend.services.run_state import RUN_STATE_FILENAME, RunState

    path = tmp_path / RUN_STATE_FILENAME
    RunState.create(path, universe_spec="all", options={}, total_tickers=10)
    payload = json.loads(path.read_text())
    del payload["price_stage"]
    path.write_text(json.dumps(payload))

    assert RunState.load(path).price_stage_status()["status"] == "ok"
