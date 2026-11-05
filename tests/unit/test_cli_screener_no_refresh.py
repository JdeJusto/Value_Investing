"""AUDIT-005: screener is read-only by default; SEC refresh is opt-in."""

from __future__ import annotations

import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from cli.commands import screener as screener_cmd


def _base_args(**overrides):
    base = {
        "tickers": "AAPL",
        "search": None,
        "fields": None,
        "filter": None,
        "revenue_growth": None,
        "no_prices": True,
        "top": 5,
        "sort": None,
        "export": None,
        "source": None,
        "compare": None,
        "investment": None,
        "pe": None,
        "pe_min": None,
        "pe_max": None,
        "pb_min": None,
        "pb_max": None,
        "roe": None,
        "roe_min": None,
        "roic_min": None,
        "net_margin": None,
        "net_margin_min": None,
        "op_margin_min": None,
        "debt_to_equity": None,
        "debt_to_equity_max": None,
        "current_ratio": None,
        "fcf_min": None,
        "fcf_yield": None,
        "fcf_yield_min": None,
        "market_cap_min": None,
        "ev_ebit_max": None,
        "sector": None,
        "top_n": 5,
        "universe": None,
        "save_watchlist": None,
        "no_save": None,
        "demo": False,
        "refresh": False,
        "no_refresh": False,
        "freshness_hours": None,
    }
    base.update(overrides)
    return Namespace(**base)


def test_screener_help_shows_refresh_opt_in():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "main.py", "screener", "--help"],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo,
    )
    out = result.stdout + result.stderr
    assert "--refresh" in out
    assert "cached data" in out.lower() or "default" in out.lower()
    assert "--no-refresh" in out
    assert "deprecated" in out.lower()


def test_screener_does_not_refresh_by_default(monkeypatch):
    calls = []

    def fake_refresh(tickers, args=None, **kwargs):
        calls.append(
            {"tickers": tickers, "no_refresh": getattr(args, "no_refresh", None)}
        )

    class _Service:
        def screen(self, **kwargs):
            return []

        def set_source_mode(self, _mode):
            return None

    monkeypatch.setattr(screener_cmd, "refresh_analysis_inputs", fake_refresh)
    monkeypatch.setattr(screener_cmd, "build_screener_service", lambda **_: _Service())
    monkeypatch.setattr(
        screener_cmd.cli_output,
        "progress",
        lambda *_a, **_k: type(
            "P",
            (),
            {
                "__enter__": lambda s: type(
                    "B",
                    (),
                    {
                        "set_total": lambda *_: None,
                        "set_description": lambda *_: None,
                        "update": lambda *_: None,
                    },
                )(),
                "__exit__": lambda *_: False,
            },
        )(),
    )

    args = _base_args()

    screener_cmd._run_screener(args)
    assert calls, (
        "screener must still call refresh hook (to warm prices / enforce policy)"
    )
    assert calls[0]["no_refresh"] is True


def test_screener_refresh_flag_opts_in(monkeypatch):
    calls = []

    def fake_refresh(tickers, args=None, **kwargs):
        calls.append(
            {
                "no_refresh": getattr(args, "no_refresh", None),
                "refresh": getattr(args, "refresh", None),
            }
        )

    class _Service:
        def screen(self, **kwargs):
            return []

        def set_source_mode(self, _mode):
            return None

    monkeypatch.setattr(screener_cmd, "refresh_analysis_inputs", fake_refresh)
    monkeypatch.setattr(screener_cmd, "build_screener_service", lambda **_: _Service())
    monkeypatch.setattr(
        screener_cmd.cli_output,
        "progress",
        lambda *_a, **_k: type(
            "P",
            (),
            {
                "__enter__": lambda s: type(
                    "B",
                    (),
                    {
                        "set_total": lambda *_: None,
                        "set_description": lambda *_: None,
                        "update": lambda *_: None,
                    },
                )(),
                "__exit__": lambda *_: False,
            },
        )(),
    )

    args = _base_args(refresh=True)

    screener_cmd._run_screener(args)
    assert calls and calls[0]["refresh"] is True
    assert calls[0]["no_refresh"] is False
