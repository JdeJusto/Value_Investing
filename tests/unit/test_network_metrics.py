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
    metrics.record_failure("sec", "sec sync failed (HTTP 403: rate limit)", latency_ms=10.0)
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
    from backend.services.price_service import PriceService

    metrics = NetworkMetrics()
    calls = {"n": 0}

    class _Ticker:
        def __init__(self, ticker):
            self.ticker = ticker

        @property
        def info(self):
            calls["n"] += 1
            raise RuntimeError("Too Many Requests")

    monkeypatch.setattr(
        "backend.services.price_service.yf.Ticker", lambda ticker: _Ticker(ticker)
    )
    monkeypatch.setattr("backend.services.price_service.time.sleep", lambda *_: None)
    service = PriceService(metrics=metrics)

    assert service.get_market_snapshots(["AAPL"], preflight=False) == {"AAPL": None}
    data = metrics.snapshot()
    assert calls["n"] == 3  # initial attempt + 2 retries
    assert data["yahoo_requests"] == 3
    assert data["yahoo_retries"] == 2  # the successful attempt carries 0


def test_price_pipeline_is_skipped_when_yahoo_is_unavailable(monkeypatch):
    """The prefetch is skipped gracefully: no HTTP call, empty mapping, N/A prices."""
    from backend.services.price_service import PriceService
    from backend.services.yahoo_health import YahooHealth

    def _boom(*args, **kwargs):  # any quote fetch would be a bug
        raise AssertionError("Yahoo must not be queried when the preflight fails")

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", _boom)

    service = PriceService(
        health_fn=lambda **kwargs: YahooHealth(False, "Yahoo unreachable", None, 0.0)
    )
    assert service.get_market_snapshots(["AAPL", "KO"]) == {}


def test_price_pipeline_runs_when_yahoo_is_available(monkeypatch):
    from backend.services.price_service import PriceService
    from backend.services.yahoo_health import YahooHealth

    class _Ticker:
        def __init__(self, ticker):
            self.ticker = ticker

        @property
        def info(self):
            return {"regularMarketPrice": 42.0}

    monkeypatch.setattr(
        "backend.services.price_service.yf.Ticker", lambda ticker: _Ticker(ticker)
    )
    service = PriceService(
        health_fn=lambda **kwargs: YahooHealth(True, "ok", 200, 0.0)
    )
    snapshots = service.get_market_snapshots(["AAPL"], preflight=True)
    assert snapshots["AAPL"]["regularMarketPrice"] == 42.0


def test_refresh_service_records_sec_sync_metrics():
    from backend.services.refresh_service import RefreshService
    from backend.services.sec_health import SecHealth

    metrics = NetworkMetrics()
    attempts: list[str] = []

    def runner(cik):
        attempts.append(cik)
        if cik == "0000000002":
            return "sec sync failed (HTTP 403: rate limit)"
        return True

    service = RefreshService(
        sec_health_fn=lambda: SecHealth(True, "ok", 200, 0.0),
        sync_runner=runner,
        metrics=metrics,
    )
    service._sync_company("0000000001")
    service._sync_company("0000000002")

    data = metrics.snapshot()
    assert data["sec_requests"] == 2
    assert data["sec_retries"] == 1
    assert data["sec_403_count"] == 1
    assert data["avg_sec_latency_ms"] >= 0


def test_report_renders_the_network_section():
    from backend.services.daily_report_service import DailyReport, build_markdown

    body = build_markdown(
        DailyReport(
            report_date=__import__("datetime").date(2026, 9, 27),
            universe_size=2528,
            screened_count=2500,
            network={
                "sec_requests": 500,
                "sec_retries": 2,
                "sec_403_count": 0,
                "sec_429_count": 1,
                "yahoo_requests": 2528,
                "yahoo_retries": 9,
                "avg_sec_latency_ms": 7240.0,
                "avg_yahoo_latency_ms": 312.5,
            },
        )
    )
    assert "## Network" in body
    assert "SEC company syncs: **500**" in body
    assert "HTTP 403/429 1" in body
    assert "Yahoo requests: **2528**" in body
    assert "312.5 ms" in body

    # No telemetry -> no section (backwards compatible reports).
    assert "## Network" not in build_markdown(
        DailyReport(report_date=__import__("datetime").date(2026, 9, 27))
    )


def test_configure_attaches_metrics_and_preflight():
    from backend.services.price_service import PriceService
    from backend.services.yahoo_health import YahooHealth

    metrics = NetworkMetrics()
    calls = []

    def fake_health(**kwargs):
        calls.append(kwargs)
        return YahooHealth(True, "ok", 200, 0.0)

    service = PriceService().configure(metrics=metrics, health_fn=fake_health)

    assert service._metrics is metrics
    assert service.yahoo_available(force=True).available is True
    assert calls == [{"force": True}]
    # a service without a preflight behaves exactly as before
    assert PriceService().yahoo_available() is None


# ----------------------------------------------------------------------
# per-category price failures
# ----------------------------------------------------------------------


def test_price_failure_categories_are_tallied():
    from backend.services.network_metrics import NetworkMetrics

    metrics = NetworkMetrics()
    metrics.note_price_failure("yahoo_glitch")
    metrics.note_price_failure("yahoo_glitch")
    metrics.note_price_failure("mapping")
    metrics.note_price_failure("no_yahoo", 2500)

    assert metrics.price_failures() == {
        "yahoo_glitch": 2,
        "mapping": 1,
        "no_yahoo": 2500,
    }


def test_price_failures_are_separate_from_http_counters():
    from backend.services.network_metrics import NetworkMetrics

    metrics = NetworkMetrics()
    metrics.record("yahoo", latency_ms=5.0)
    metrics.note_price_failure("delisted", 3)

    assert metrics.snapshot()["yahoo_requests"] == 1
    assert metrics.price_failures() == {"delisted": 3}


def test_price_failure_tally_is_thread_safe():
    from backend.services.network_metrics import NetworkMetrics

    metrics = NetworkMetrics()

    def worker(n: int) -> None:
        for _ in range(200):
            metrics.note_price_failure(f"cat{n}")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert metrics.price_failures() == {f"cat{n}": 200 for n in range(6)}


def test_classify_price_failure_tallies_every_category(monkeypatch):
    from backend.services.network_metrics import NetworkMetrics
    from backend.services.price_service import PriceService

    metrics = NetworkMetrics()
    service = PriceService(metrics=metrics)
    # The control symbol (AAPL) is what tells the classifier the provider is
    # answering; a ticker-aware probe keeps the per-symbol verdicts honest.
    monkeypatch.setattr(service, "_probe_has_data", lambda ticker: ticker == "AAPL")
    assert service.classify_price_failure("AAPL") == "yahoo_glitch"

    # Only the symbol under test lacks data: the control symbol still answers,
    # which is what makes a per-symbol verdict safe. A provider-wide outage is
    # covered separately (it must never be tallied as delisted).
    monkeypatch.setattr(service, "_probe_has_data", lambda ticker: ticker == "AAPL")
    assert service.classify_price_failure(
        "MSFT", known_ticker=lambda t: False
    ) == "mapping"
    assert service.classify_price_failure(
        "MSFT", known_ticker=lambda t: True
    ) == "delisted"
    assert service.classify_price_failure("MSFT") == "unknown"  # no listing opinion

    assert metrics.price_failures() == {
        "yahoo_glitch": 1,
        "mapping": 1,
        "delisted": 1,
        "unknown": 1,
    }
    assert service.price_failure_counts() == metrics.price_failures()


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
