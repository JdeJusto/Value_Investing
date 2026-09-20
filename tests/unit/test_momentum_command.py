"""Regression tests for the momentum CLI command.

Covers the fix for the `TypeError: expected string or bytes-like object,
got 'int'` crash: the momentum command passes a raw int row index into the
table formatter, which calls `remove_ansi()` on every cell. The index is now
stringified before rendering.

These tests run the command against mocked analysis results and assert it
renders a ranking table without raising.
"""

import argparse

import pytest

import cli.commands.momentum as momentum_command


class _FakeAnalysisService:
    """Stands in for CompanyAnalysisService with a canned analyze()."""

    def __init__(self, results):
        self._results = results

    def analyze(self, ticker):
        return self._results.get(ticker)


def _analysis(ticker, deltas=None):
    return {
        "ticker": ticker,
        "delta_metrics": deltas
        or {
            "revenue_growth_delta": 0.04,
            "gross_margin_delta": 0.01,
            "roic_delta": -0.02,
            "fcf_delta": 0.03,
        },
    }


@pytest.fixture
def fake_services(monkeypatch):
    results = {
        "AAPL": _analysis(
            "AAPL",
            {
                "revenue_growth_delta": 0.05,
                "gross_margin_delta": 0.0,
                "roic_delta": 0.0,
                "fcf_delta": 0.0,
            },
        ),
        "MSFT": _analysis(
            "MSFT",
            {
                "revenue_growth_delta": 0.01,
                "gross_margin_delta": 0.01,
                "roic_delta": 0.02,
                "fcf_delta": 0.01,
            },
        ),
        "KO": _analysis(
            "KO",
            {
                "revenue_growth_delta": 0.0,
                "gross_margin_delta": 0.0,
                "roic_delta": -0.01,
                "fcf_delta": 0.02,
            },
        ),
    }
    monkeypatch.setattr(
        momentum_command,
        "build_analysis_service",
        lambda: _FakeAnalysisService(results),
    )
    monkeypatch.setattr(
        momentum_command,
        "build_universe",
        lambda tickers: tickers or ["AAPL", "MSFT", "KO"],
    )
    return results


def _run(*tickers):
    args = argparse.Namespace(tickers=list(tickers))
    momentum_command._run(args)


def test_momentum_multiple_tickers_renders_table_without_typeerror(
    fake_services, capsys
):
    _run("AAPL", "MSFT", "KO")
    out = capsys.readouterr().out
    assert "Momentum fundamental" in out
    assert "AAPL" in out
    assert "MSFT" in out
    assert "KO" in out


def test_momentum_single_ticker_renders(fake_services, capsys):
    _run("AAPL")
    out = capsys.readouterr().out
    assert "Momentum fundamental" in out
    assert "AAPL" in out


def test_momentum_without_tickers_uses_universe(fake_services, capsys):
    _run()
    out = capsys.readouterr().out
    assert "Momentum fundamental" in out
    assert "AAPL" in out and "MSFT" in out and "KO" in out


def test_momentum_no_services_does_not_crash(monkeypatch, capsys):
    """analyze() returning None (no data) must degrade to an empty message."""
    monkeypatch.setattr(
        momentum_command,
        "build_analysis_service",
        lambda: _FakeAnalysisService({}),
    )
    monkeypatch.setattr(
        momentum_command, "build_universe", lambda tickers: ["AAPL", "MSFT"]
    )
    _run("AAPL", "MSFT")
    out = capsys.readouterr().out
    assert "Sin datos para evaluar" in out