"""Screener `--methodology` filter and the analysis-cache wiring (hermetic)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.methodologies.base import Verdict
from backend.methodologies.registry import registry
from backend.services.screener_service import StockScreenerService


class _Repo:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def get_best_available(self, ticker, max_years=None):
        self.calls += 1
        return list(self.rows)


class _Prices:
    def get_current_price(self, ticker):
        return 100.0

    def get_market_cap(self, ticker):
        return 1_000_000.0


class _Method:
    def __init__(self, verdict):
        self.verdict = verdict

    def evaluate(self, ticker, rows, prices):
        return SimpleNamespace(verdict=self.verdict)


def _service(rows=({"fiscal_year": 2025},)):
    repository = _Repo(rows)
    service = StockScreenerService(
        repository=repository,
        market_provider=SimpleNamespace(get_company_name=lambda ticker: "Test"),
        price_service=_Prices(),
    )
    return service, repository


def _patch_registry(monkeypatch, verdicts):
    monkeypatch.setattr(
        registry,
        "get",
        lambda name: _Method(verdicts[name]) if name in verdicts else None,
    )


def test_methodology_filter_requires_every_pair(monkeypatch):
    service, _ = _service()
    _patch_registry(monkeypatch, {"graham": Verdict.BUY, "lynch_garp": Verdict.AVOID})

    assert service._passes_methodology("AAPL", [("graham", "BUY")]) is True
    assert (
        service._passes_methodology("AAPL", [("graham", "BUY"), ("lynch_garp", "BUY")])
        is False
    )


def test_methodology_rows_are_read_once_per_ticker(monkeypatch):
    service, repository = _service()
    _patch_registry(monkeypatch, {"graham": Verdict.BUY})

    service._passes_methodology("AAPL", [("graham", "BUY")])
    service._passes_methodology("AAPL", [("graham", "BUY")])

    assert repository.calls == 1


def test_unknown_methodology_never_matches(monkeypatch):
    service, _ = _service()
    _patch_registry(monkeypatch, {})
    assert service._passes_methodology("AAPL", [("nope", "BUY")]) is False


def test_no_fundamentals_never_matches(monkeypatch):
    service, _ = _service(rows=())
    _patch_registry(monkeypatch, {"graham": Verdict.BUY})
    assert service._passes_methodology("AAPL", [("graham", "BUY")]) is False


def test_screener_service_passes_the_analysis_cache():
    cache = object()
    service = StockScreenerService(
        repository=_Repo([]),
        market_provider=SimpleNamespace(get_company_name=lambda ticker: "Test"),
        price_service=_Prices(),
        analysis_cache=cache,
    )
    assert service._analysis._history_cache is cache


@pytest.mark.parametrize(
    "raw,expected",
    [
        (["graham:BUY"], [("graham", "BUY")]),
        (["lynch:watch"], [("lynch_garp", "WATCH")]),
        (["graham:na"], [("graham", "N/A")]),
    ],
)
def test_cli_parses_methodology_filters(raw, expected):
    from cli.commands.screener import _parse_methodology_filters

    assert _parse_methodology_filters(raw) == expected


@pytest.mark.parametrize("raw", [["graham"], ["nope:BUY"], ["graham:MAYBE"]])
def test_cli_rejects_bad_methodology_filters(raw):
    from cli.commands.screener import _parse_methodology_filters

    with pytest.raises(SystemExit) as exit_info:
        _parse_methodology_filters(raw)
    assert exit_info.value.code == 1
