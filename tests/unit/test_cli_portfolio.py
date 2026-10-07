"""CLI `portfolio`: panel banner, positions table, thesis and performance."""

from __future__ import annotations

import io
import sys
from argparse import Namespace
from typing import ClassVar

import pytest

from backend.services import cli_output
from cli.commands import portfolio

ESC = "\x1b"


class _TTY(io.StringIO):
    """A stdout stand-in that claims to be a terminal."""

    def isatty(self) -> bool:  # pragma: no cover - trivial
        return True


@pytest.fixture(autouse=True)
def _clean_color_state():
    cli_output.reset_no_color()
    yield
    cli_output.reset_no_color()


def _position(**overrides):
    row = {
        "ticker": "AAPL",
        "quantity": 10,
        "current_price": 200.0,
        "unrealized_return": 0.25,
        "buffett_score": 72.0,
        "moat": "WIDE",
        "signal": "BUY",
        "opportunity_type": "undervalued",
        "thesis": "Services growth keeps compounding.",
    }
    row.update(overrides)
    return row


def _performance() -> dict:
    return {
        "market_value": 4000.0,
        "cost_basis": 3000.0,
        "unrealized_pnl": 1000.0,
        "realized_pnl": 50.0,
        "total_pnl": 1050.0,
        "total_return": 0.35,
        "allocation": {
            "overconcentrated": [{"ticker": "AAPL", "weight": 0.60, "threshold": 0.25}],
            "sector_exposure": [{"sector": "Technology", "weight": 0.75}],
            "risk": {
                "largest_position_weight": 0.60,
                "top_n_share": 0.90,
                "hhi": 0.412,
            },
        },
    }


class _Service:
    positions: ClassVar[list] = []
    perf: ClassVar[dict] = {}

    def view(self):
        return list(type(self).positions)

    def performance(self):
        return dict(type(self).perf)


def _patch(monkeypatch, positions: list, perf: dict | None = None) -> None:
    _Service.positions = positions
    _Service.perf = perf or {}
    monkeypatch.setattr(portfolio, "build_portfolio_service", lambda: _Service())


def test_view_renders_banner_table_and_thesis(monkeypatch, capsys):
    _patch(
        monkeypatch,
        [_position(), _position(ticker="MSFT", thesis=None, unrealized_return=-0.10)],
    )
    portfolio._view(Namespace())
    out = capsys.readouterr().out

    assert "Portfolio (2 positions)" in out
    assert "╭" in out and "╰" in out  # banner panel
    assert "Ticker" in out and "AAPL" in out and "MSFT" in out
    assert "Thesis" in out
    assert "Services growth keeps compounding." in out
    assert "(no thesis)" in out
    assert ESC not in out


def test_view_marks_gains_and_losses_with_palette_colors(monkeypatch):
    """On a terminal the return cell keeps its green/red styling (Rich
    parses the escape sequences so the column width stays correct)."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _TTY())
    _patch(monkeypatch, [_position(), _position(ticker="KO", unrealized_return=-0.05)])

    portfolio._view(Namespace())
    out = sys.stdout.getvalue()

    assert "AAPL" in out and "KO" in out
    assert ESC in out


def test_performance_lists_findings_and_sector_exposure(monkeypatch, capsys):
    _patch(monkeypatch, [_position()], _performance())
    portfolio._performance(Namespace())
    out = capsys.readouterr().out

    assert "Portfolio performance" in out
    assert "Market value" in out and "$4.0K" in out
    assert "Overconcentration" in out
    assert "AAPL: 60% (limit 25%)" in out
    assert "Sector exposure" in out
    assert "Technology: 75%" in out
    assert "Concentration risk" in out
    assert "HHI" in out and "0.412" in out
    assert ESC not in out


def test_performance_says_when_nothing_is_overconcentrated(monkeypatch, capsys):
    perf = _performance()
    perf["allocation"]["overconcentrated"] = []
    _patch(monkeypatch, [_position()], perf)
    portfolio._performance(Namespace())
    out = capsys.readouterr().out

    assert "No overconcentration." in out
    assert "Overconcentration" not in out


def test_view_empty_portfolio_points_to_the_add_command(monkeypatch, capsys):
    _patch(monkeypatch, [])
    portfolio._view(Namespace())
    out = capsys.readouterr().out

    assert "Portfolio (0 positions)" in out
    assert "Empty portfolio." in out
    assert "portfolio add" in out


def test_thesis_line_styles_the_ticker_and_mutes_missing_thesis():
    line = portfolio._thesis_line("AAPL", "Buy and hold.")
    assert str(line) == "  AAPL: Buy and hold."
    empty = portfolio._thesis_line("KO", None)
    assert str(empty) == "  KO: (no thesis)"
