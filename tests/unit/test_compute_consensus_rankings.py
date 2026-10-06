"""Consensus computation: price prefetch, fallbacks and idempotent output."""

from __future__ import annotations

import json
from types import SimpleNamespace

import scripts.compute_consensus_rankings as consensus
from backend.services.consensus_service import CONSENSUS_VERSION


class FakePriceService:
    """PriceService stand-in: no network, records the calls it receives."""

    def __init__(self, *, snapshots=None, current=None, health=None):
        self._snapshots = snapshots or {}
        self._current = current or {}
        self._health = health
        self.snapshot_calls = 0
        self.current_calls = 0
        self.snapshot_tickers: list[str] = []

    def yahoo_available(self, force=False):
        return self._health

    def get_market_snapshots(self, tickers, **kwargs):
        self.snapshot_calls += 1
        self.snapshot_tickers = list(tickers)
        return self._snapshots

    def get_current_prices(self, tickers, **kwargs):
        self.current_calls += 1
        return self._current


class FakeRepository:
    def get_best_available(self, ticker, max_years=10):
        return [SimpleNamespace(ticker=ticker)]


def _healthy():
    return SimpleNamespace(available=True, reason="ok")


def _down():
    return SimpleNamespace(available=False, reason="429")


def _view(category: str = "STALWART") -> SimpleNamespace:
    details = [
        {"methodology": name, "verdict": "BUY"} for name in consensus.METHODOLOGY_KEYS
    ]
    # METHODOLOGY_KEYS[-2] is lynch_garp.
    details[-2]["category"] = category
    return SimpleNamespace(details=details)


def test_prefetch_uses_one_batch_snapshot_for_the_universe():
    service = FakePriceService(
        snapshots={
            "AAPL": {"regularMarketPrice": 250.0, "marketCap": 3.8e12},
            "MSFT": {"regularMarketPrice": 500.0},
        },
        health=_healthy(),
    )
    prices, caps, available = consensus.prefetch_prices(service, ["AAPL", "MSFT"])
    assert prices == {"AAPL": 250.0, "MSFT": 500.0}
    assert caps == {"AAPL": 3.8e12}
    assert available is True
    assert service.snapshot_calls == 1
    assert service.snapshot_tickers == ["AAPL", "MSFT"]
    assert service.current_calls == 0


def test_prefetch_skips_everything_when_the_preflight_fails():
    service = FakePriceService(
        snapshots={"AAPL": {"regularMarketPrice": 250.0}}, health=_down()
    )
    prices, caps, available = consensus.prefetch_prices(service, ["AAPL"])
    assert (prices, caps, available) == ({}, {}, False)
    assert service.snapshot_calls == 0
    assert service.current_calls == 0


def test_prefetch_falls_back_to_per_ticker_prices():
    service = FakePriceService(
        snapshots={},
        current={"AAPL": 111.0, "MSFT": None},
        health=_healthy(),
    )
    prices, caps, available = consensus.prefetch_prices(service, ["AAPL", "MSFT"])
    assert prices == {"AAPL": 111.0}
    assert caps == {}
    assert available is True
    assert service.snapshot_calls == 1
    assert service.current_calls == 1


def test_prefetch_reports_unavailable_when_both_paths_fail():
    service = FakePriceService(snapshots={}, current={}, health=_healthy())
    assert consensus.prefetch_prices(service, ["AAPL"]) == ({}, {}, False)
    assert service.snapshot_calls == 1
    assert service.current_calls == 1


def test_build_company_consensus_records_price_and_category():
    row = consensus.build_company_consensus(
        "AAPL",
        "Apple Inc.",
        _view(),
        price=254.52,
        prices_available=True,
    )
    assert row["price"] == 254.52
    assert row["prices_available"] is True
    assert row["lynch_category"] == "STALWART"
    assert row["buy_count"] == 8


def test_write_report_is_idempotent(tmp_path):
    payload = {
        "version": CONSENSUS_VERSION,
        "date": "2026-10-06",
        "universe": "sp500",
        "prices_available": False,
        "prices_snapshot": {},
        "companies": {},
    }
    first = consensus.write_report(tmp_path, "2026-10-06", payload)
    first_bytes = first.read_bytes()
    second = consensus.write_report(tmp_path, "2026-10-06", payload)
    assert second == first
    assert second.read_bytes() == first_bytes


def test_main_wires_prices_and_writes_schema_v2(monkeypatch, tmp_path):
    service = FakePriceService(
        snapshots={
            "AAPL": {"regularMarketPrice": 250.0, "marketCap": 3.8e12},
            "MSFT": {"regularMarketPrice": 500.0, "marketCap": 3.7e12},
        },
        health=_healthy(),
    )
    calls: list[tuple] = []

    def fake_run_methodologies(ticker, rows, price=None, market_cap=None):
        calls.append((ticker, price, market_cap))
        return _view()

    monkeypatch.setattr(
        consensus,
        "read_universe",
        lambda source, path=None: (["AAPL", "MSFT"], {"AAPL": "Apple Inc."}),
    )
    monkeypatch.setattr(consensus, "build_financial_repository", FakeRepository)
    monkeypatch.setattr(consensus, "discover", lambda: 0)
    monkeypatch.setattr(consensus, "get_price_service", lambda: service)
    monkeypatch.setattr(consensus, "run_methodologies", fake_run_methodologies)

    args = [
        "--universe",
        "sp500",
        "--limit",
        "2",
        "--date",
        "2026-10-06",
        "--output-dir",
        str(tmp_path),
    ]
    assert consensus.main(args) == 0
    first_bytes = (tmp_path / "consensus_2026-10-06.json").read_bytes()

    payload = json.loads(first_bytes)
    assert payload["version"] == CONSENSUS_VERSION == 2
    assert payload["prices_available"] is True
    assert payload["prices_snapshot"] == {"AAPL": 250.0, "MSFT": 500.0}
    assert payload["companies"]["AAPL"]["price"] == 250.0
    assert payload["companies"]["AAPL"]["prices_available"] is True
    assert payload["companies"]["MSFT"]["price"] == 500.0
    # Prices and market caps reached the methodologies (A5).
    assert ("AAPL", 250.0, 3.8e12) in calls
    assert ("MSFT", 500.0, 3.7e12) in calls

    assert consensus.main(args) == 0
    assert (tmp_path / "consensus_2026-10-06.json").read_bytes() == first_bytes
