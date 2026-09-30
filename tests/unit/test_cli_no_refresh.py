"""Regression: the refresh flags are wired across the six analyze-* commands.

Each command must call ``refresh_analysis_inputs`` with the parsed flags:
``--no-refresh`` -> skip_refresh (no_refresh=True), default -> refresh
attempt allowed, ``--refresh`` -> force. The refresh helper is stubbed, so
no network or database is touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from cli.main import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

COMMANDS = [
    "analyze-graham",
    "analyze-graham-dodd",
    "analyze-buffett-classic",
    "analyze-buffett-clark",
    "analyze-fisher-quant",
    "analyze-lynch-garp",
]


class _Prices:
    def __init__(self, price=100.0):
        self._price = price

    def get_current_price(self, ticker):
        return self._price


class _Repo:
    def get_best_available(self, ticker):
        rows = json.loads((FIXTURES / "graham_pass.json").read_text())
        return [NormalizedFinancials.from_dict(row) for row in rows]


def _run(argv, monkeypatch):
    calls = []

    def fake_refresh(tickers, args=None, **kwargs):
        calls.append(
            {
                "tickers": list(tickers),
                "no_refresh": getattr(args, "no_refresh", None),
                "refresh": getattr(args, "refresh", None),
                "freshness_hours": getattr(args, "freshness_hours", None),
            }
        )

    monkeypatch.setattr(sys, "argv", ["main.py"] + argv)
    monkeypatch.setattr("backend.app.cli.build_financial_repository", lambda: _Repo())
    monkeypatch.setattr(
        "backend.services.price_service.get_price_service", lambda: _Prices()
    )
    monkeypatch.setattr("backend.app.cli.refresh_analysis_inputs", fake_refresh)
    main()
    return calls


@pytest.mark.parametrize("command", COMMANDS)
def test_no_refresh_flag_is_wired(command, monkeypatch, capsys):
    calls = _run([command, "AAPL", "--no-refresh"], monkeypatch)
    capsys.readouterr()
    assert calls and calls[0]["tickers"] == ["AAPL"]
    assert calls[0]["no_refresh"] is True


@pytest.mark.parametrize("command", COMMANDS)
def test_default_does_not_skip_refresh(command, monkeypatch, capsys):
    calls = _run([command, "AAPL"], monkeypatch)
    capsys.readouterr()
    assert calls and calls[0]["no_refresh"] is False


@pytest.mark.parametrize("command", COMMANDS)
def test_refresh_flag_is_wired(command, monkeypatch, capsys):
    calls = _run([command, "AAPL", "--refresh"], monkeypatch)
    capsys.readouterr()
    assert calls and calls[0]["refresh"] is True
