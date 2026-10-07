"""CLI `screener`: the batch screen drives the shared progress helper.

The screen loop streams per-ticker updates through ``progress_callback``.
Those updates go to :func:`cli_output.progress`, which draws a Rich bar on
a terminal and stays completely silent when stdout is redirected (the old
inline bar wrote carriage returns into pipes).
"""

from __future__ import annotations

import argparse
import io
import sys
from typing import ClassVar

import pytest

from backend.services import cli_output
from cli.commands import screener

ESC = "\x1b"


class _TTY(io.StringIO):
    """A stdout stand-in that claims to be a terminal."""

    def isatty(self) -> bool:  # pragma: no cover - trivial
        return True


class _Service:
    last: ClassVar[dict] = {}
    callbacks: ClassVar[list] = []

    def screen(self, *, tickers, filters, top_n, progress_callback, no_prices):
        type(self).last = {
            "tickers": tickers,
            "top_n": top_n,
            "no_prices": no_prices,
        }
        type(self).callbacks = []
        for index, ticker in enumerate(tickers or [], 1):
            if progress_callback:
                progress_callback(index, len(tickers), ticker)
                type(self).callbacks.append(ticker)
        return []


@pytest.fixture(autouse=True)
def _clean_color_state():
    cli_output.reset_no_color()
    yield
    cli_output.reset_no_color()


def _patch(monkeypatch) -> None:
    _Service.last = {}
    _Service.callbacks = []
    monkeypatch.setattr(screener, "build_screener_service", lambda: _Service())
    monkeypatch.setattr(
        screener, "refresh_analysis_inputs", lambda *args, **kwargs: None
    )


def _args(argv: list[str]):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    screener.register(sub)
    return parser.parse_args(argv)


def test_screen_run_is_plain_when_redirected(monkeypatch, capsys):
    _patch(monkeypatch)
    screener._run_screener(_args(["screener", "--tickers", "AAPL,MSFT"]))

    out = capsys.readouterr().out
    assert _Service.last["tickers"] == ["AAPL", "MSFT"]
    assert _Service.callbacks == ["AAPL", "MSFT"]  # every ticker reported
    assert "results in" in out
    assert "\r" not in out  # no inline redraw leaked into the pipe
    assert ESC not in out


def test_screen_run_drives_the_progress_bar_on_a_terminal(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _TTY())
    _patch(monkeypatch)

    screener._run_screener(_args(["screener", "--tickers", "AAPL,MSFT"]))

    out = sys.stdout.getvalue()
    assert ESC in out  # the bar is drawn
    assert "Screening MSFT" in out  # caption follows the current ticker
    assert "2/2" in out  # completed/total from the callbacks
