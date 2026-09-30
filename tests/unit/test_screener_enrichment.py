"""Screener enrichment: parallel results match sequential, failures isolate."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.services.ui_adapter import enrich_rows


@dataclass
class _View:
    details: list = field(default_factory=list)
    category: str | None = None


def _make_loaders(failing: set[str] | None = None, exploding: set[str] | None = None):
    failing = failing or set()
    exploding = exploding or set()
    calls: list[str] = []

    def load_fundamentals(ticker):
        calls.append(ticker)
        if ticker in failing:
            raise RuntimeError("db down for this ticker")
        return [] if ticker in exploding else [object()]

    def run_methodologies(ticker, fundamentals, price):
        if ticker in exploding:
            raise RuntimeError("evaluation blew up")
        return _View(
            details=[{"methodology": "buffett_classic", "verdict": "BUY", "score": 80.0}],
            category="Quality",
        )

    return load_fundamentals, run_methodologies, calls


def _rows(tickers):
    return [{"ticker": t, "price": 10.0, "name": t} for t in tickers]


def test_parallel_matches_sequential():
    load, run, _ = _make_loaders()
    rows = _rows(["AAPL", "KO", "JPM", "XOM"])
    sequential = enrich_rows(rows, "buffett_classic", {}, load, run, workers=1)
    parallel = enrich_rows(rows, "buffett_classic", {}, load, run, workers=4)
    assert parallel == sequential
    assert [r["Verdict"] for r in parallel] == ["BUY"] * 4


def test_order_is_preserved():
    load, run, _ = _make_loaders()
    tickers = ["AAPL", "KO", "JPM", "XOM", "F"]
    out = enrich_rows(_rows(tickers), "buffett_classic", {}, load, run, workers=4)
    assert [r["Ticker"] for r in out] == tickers


def test_one_failure_does_not_crash_the_batch():
    load, run, _ = _make_loaders(failing={"KO"}, exploding={"JPM"})
    out = enrich_rows(
        _rows(["AAPL", "KO", "JPM", "XOM"]), "buffett_classic", {}, load, run, workers=4
    )
    by_ticker = {r["Ticker"]: r for r in out}
    assert by_ticker["KO"]["Verdict"] is None  # loader failed
    assert by_ticker["JPM"]["Verdict"] is None  # evaluation failed
    assert by_ticker["AAPL"]["Verdict"] == "BUY"
    assert by_ticker["XOM"]["Verdict"] == "BUY"


def test_loader_called_once_per_ticker():
    load, run, calls = _make_loaders()
    tickers = ["AAPL", "KO", "JPM"]
    enrich_rows(_rows(tickers), "buffett_classic", {}, load, run, workers=4)
    assert sorted(calls) == sorted(tickers)


def test_single_row_skips_the_pool():
    load, run, _ = _make_loaders()
    out = enrich_rows(_rows(["AAPL"]), "buffett_classic", {}, load, run, workers=4)
    assert out[0]["Verdict"] == "BUY"
