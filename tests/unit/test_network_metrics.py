"""Unit tests for the per-run network telemetry (Phase 5)."""

from __future__ import annotations

import threading

from backend.services.network_metrics import NETWORK_FIELDS, NetworkMetrics


def test_snapshot_always_exposes_every_field():
    data = NetworkMetrics().snapshot()
    assert set(data) == set(NETWORK_FIELDS)
    assert all(value == 0 for value in data.values())


def test_counters_accumulate_and_average_latency():
    metrics = NetworkMetrics()
    metrics.record("yahoo", latency_ms=100.0)
    metrics.record("yahoo", latency_ms=300.0, retries=1)

    data = metrics.snapshot()
    assert data["yahoo_requests"] == 2
    assert data["yahoo_retries"] == 1
    assert data["avg_yahoo_latency_ms"] == 200.0
    assert data["sec_requests"] == 0


def test_sec_throttling_is_counted_from_status_and_reason():
    metrics = NetworkMetrics()
    metrics.record("sec", latency_ms=7240.0)
    metrics.record_failure(
        "sec", "sec sync failed (HTTP 403: rate limit)", latency_ms=10.0
    )
    metrics.record("sec", http_status=429, latency_ms=5.0)
    metrics.record("sec", reason="timeout while fetching companyfacts", latency_ms=7.0)

    data = metrics.snapshot()
    assert data["sec_requests"] == 4
    assert data["sec_retries"] == 1  # only the failure counts as a retry
    assert data["sec_403_count"] == 1
    assert data["sec_429_count"] == 1
    assert data["avg_sec_latency_ms"] == 1815.5  # (7240 + 10 + 5 + 7) / 4


def test_note_status_only_counts_throttling():
    metrics = NetworkMetrics()
    metrics.note_status("yahoo", 200)
    metrics.note_status("yahoo", 429)
    assert metrics.snapshot()["yahoo_requests"] == 1


def test_empty_and_summary():
    metrics = NetworkMetrics()
    assert metrics.is_empty() is True
    assert "no calls" in metrics.summary()

    metrics.record("sec", latency_ms=7000.0)
    metrics.record("yahoo", latency_ms=250.0)
    assert metrics.is_empty() is False
    summary = metrics.summary()
    assert "SEC syncs 1" in summary
    assert "Yahoo requests 1" in summary
    assert "7000 ms" in summary


def test_concurrent_updates_are_not_lost():
    metrics = NetworkMetrics()
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for _ in range(200):
                metrics.record("yahoo", latency_ms=10.0, retries=1)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    data = metrics.snapshot()
    assert data["yahoo_requests"] == 8 * 200
    assert data["yahoo_retries"] == 8 * 200


# ----------------------------------------------------------------------
# wiring: PriceService, RefreshService and the report
# ----------------------------------------------------------------------


def test_price_service_records_yahoo_attempts(monkeypatch):
    from backend.services.price_service import PriceService

    metrics = NetworkMetrics()

    class _Ticker:
        def __init__(self, ticker):
            self.ticker = ticker

        @property
        def info(self):
            return {"regularMarketPrice": 100.0}

    monkeypatch.setattr(
        "backend.services.price_service.yf.Ticker", lambda ticker: _Ticker(ticker)
    )
    service = PriceService(metrics=metrics)
    snapshots = service.get_market_snapshots(["AAPL", "KO"], preflight=False)

    assert len(snapshots) == 2
    data = metrics.snapshot()
    assert data["yahoo_requests"] == 2
    assert data["yahoo_retries"] == 0
    assert data["avg_yahoo_latency_ms"] >= 0


def test_price_service_counts_retries_and_failures(monkeypatch):
    """A transient failure still retries, and every attempt is counted."""
    from backend.services.price_service import PriceService

    metrics = NetworkMetrics()
    calls = {"n": 0}

    class _Ticker:
        def __init__(self, ticker):
            self.ticker = ticker

        @property
        def info(self):
            calls["n"] += 1
            raise TimeoutError("timed out")

    monkeypatch.setattr(
        "backend.services.price_service.yf.Ticker", lambda ticker: _Ticker(ticker)
    )
    monkeypatch.setattr("backend.services.price_service.time.sleep", lambda *_: None)
    service = PriceService(metrics=metrics)

    assert service.get_market_snapshots(["AAPL"], preflight=False) == {"AAPL": None}
    data = metrics.snapshot()
    assert calls["n"] == 3  # initial attempt + 2 retries (transient)
    assert data["yahoo_requests"] == 3
    assert data["yahoo_retries"] == 2  # the successful attempt carries 0


def test_non_transient_failures_are_counted_without_retrying(monkeypatch):
    """A 429 is one request, not three: retrying it is what causes a throttle."""
    from backend.services.price_service import PriceService

    metrics = NetworkMetrics()
    calls = {"n": 0}

    class _RateLimit(Exception):
        pass

    _RateLimit.__name__ = "YFRateLimitError"

    class _Ticker:
        def __init__(self, ticker):
            self.ticker = ticker

        @property
        def info(self):
            calls["n"] += 1
            raise _RateLimit("Too Many Requests. Rate limited.")

    monkeypatch.setattr(
        "backend.services.price_service.yf.Ticker", lambda ticker: _Ticker(ticker)
    )
    monkeypatch.setattr("backend.services.price_service.time.sleep", lambda *_: None)
    service = PriceService(metrics=metrics, abort_after=0)

    assert service.get_market_snapshots(["AAPL"], preflight=False) == {"AAPL": None}
    data = metrics.snapshot()
    assert calls["n"] == 1
    assert data["yahoo_requests"] == 1
    assert data["yahoo_retries"] == 0


def test_no_yahoo_is_counted_without_probing(monkeypatch):
    from backend.services.network_metrics import NetworkMetrics
    from backend.services.price_service import PriceService

    metrics = NetworkMetrics()
    service = PriceService(metrics=metrics)

    def _boom(ticker):  # no probe must be attempted
        raise AssertionError("no probe when Yahoo is known down")

    monkeypatch.setattr(service, "_probe_has_data", _boom)
    service.note_no_yahoo(2528)

    assert metrics.price_failures() == {"no_yahoo": 2528}


def test_price_failure_counts_without_telemetry_is_empty():
    from backend.services.price_service import PriceService

    assert PriceService().price_failure_counts() == {}


def test_report_renders_the_price_stage_section():
    from datetime import date as _date

    from backend.services.daily_report_service import DailyReport, build_markdown

    body = build_markdown(
        DailyReport(
            report_date=_date(2026, 9, 27),
            universe_size=2528,
            prices_stage={
                "processed": 2528,
                "failures": {"yahoo_glitch": 12, "mapping": 3, "no_yahoo": 2513},
            },
        )
    )
    assert "## Price stage" in body
    assert "Tickers processed: **2528**" in body
    assert "yahoo_glitch: 12" in body
    assert "mapping: 3" in body
    assert "no_yahoo: 2513" in body


def test_report_explains_a_pure_no_yahoo_stage():
    from datetime import date as _date

    from backend.services.daily_report_service import DailyReport, build_markdown

    body = build_markdown(
        DailyReport(
            report_date=_date(2026, 9, 27),
            prices_stage={"processed": 25, "failures": {"no_yahoo": 25}},
        )
    )
    assert "Failures by category — no_yahoo: 25" in body
    assert "preflight found the provider unreachable" in body


def test_report_omits_the_section_when_there_are_no_prices():
    from datetime import date as _date

    from backend.services.daily_report_service import DailyReport, build_markdown

    assert "## Price stage" not in build_markdown(
        DailyReport(report_date=_date(2026, 9, 27))
    )
    assert "Failures by category — none" in build_markdown(
        DailyReport(
            report_date=_date(2026, 9, 27),
            prices_stage={"processed": 500, "failures": {}},
        )
    )
