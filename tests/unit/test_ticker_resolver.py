"""Tests for the ticker resolver and the analyze-full preflight.

The resolver is exercised with a fake psycopg2 connection; the CLI tests
patch the command module's imports (module-level names) and never touch the
database or the network.
"""

from __future__ import annotations

import sys

import pytest

from backend.services.ticker_resolver import resolve_ticker
from cli.main import main


class _Cursor:
    def __init__(self, found):
        self._found = found

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.params = params

    def fetchone(self):
        return (1,) if self._found else None


class _Conn:
    def __init__(self, found):
        self._found = found

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _Cursor(self._found)


def test_resolve_ticker_normalizes(monkeypatch):
    monkeypatch.setattr(
        "backend.services.ticker_resolver.psycopg2.connect",
        lambda url: _Conn(True),
    )
    assert resolve_ticker("  aapl ") == "AAPL"


def test_resolve_ticker_unknown_returns_none(monkeypatch):
    monkeypatch.setattr(
        "backend.services.ticker_resolver.psycopg2.connect",
        lambda url: _Conn(False),
    )
    assert resolve_ticker("ZZZZ") is None


def test_resolve_ticker_empty_returns_none():
    assert resolve_ticker("") is None


def test_analyze_full_unknown_ticker_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "analyze-full", "ZZZZ"])
    monkeypatch.setattr(
        "backend.services.ticker_resolver.resolve_ticker", lambda ticker: None
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "not found in Financial-DataBase" in out
    assert "daily_workflow --refresh" in out


def test_analyze_full_valid_ticker_continues(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "analyze-full", "AAPL"])
    monkeypatch.setattr(
        "backend.services.ticker_resolver.resolve_ticker",
        lambda ticker: ticker.upper(),
    )
    monkeypatch.setattr(
        "cli.commands.analyze_full.refresh_analysis_inputs", lambda *a, **k: None
    )

    class _Service:
        def _analyze_ticker(self, ticker, no_prices=False):
            return None  # degrades to the "sin datos suficientes" path

    monkeypatch.setattr(
        "cli.commands.analyze_full.build_screener_service", lambda: _Service()
    )
    main()  # must not raise SystemExit
    out = capsys.readouterr().out
    assert "Not enough data for" in out
