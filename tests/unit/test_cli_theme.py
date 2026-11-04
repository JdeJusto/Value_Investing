"""Tests for the opt-in synthwave CLI theme."""

from __future__ import annotations

import io
import sys

import pytest

from backend.services import cli_output
from cli import theme


class _TTY(io.StringIO):
    def isatty(self) -> bool:  # pragma: no cover - trivial
        return True


@pytest.fixture(autouse=True)
def _clean_color_state():
    cli_output.reset_no_color()
    yield
    cli_output.reset_no_color()


def test_header_emits_ansi_on_a_terminal(monkeypatch):
    out = _TTY()
    monkeypatch.setattr(sys, "stdout", out)
    theme.print_header("Financials", "AAPL")

    assert "\x1b[" in out.getvalue()
    assert "Financials" in out.getvalue()


def test_disable_removes_ansi_on_a_terminal(monkeypatch):
    out = _TTY()
    monkeypatch.setattr(sys, "stdout", out)
    theme.disable()
    theme.print_header("Financials")

    assert "\x1b[" not in out.getvalue()


def test_verdict_and_big_number_are_colored(monkeypatch):
    out = _TTY()
    monkeypatch.setattr(sys, "stdout", out)
    print(theme.color_verdict("BUY"), theme.color_big_number("8.4"))

    value = out.getvalue()
    assert "\x1b[" in value
    assert "BUY" in value and "8.4" in value


def test_no_color_environment_is_honored(monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    theme.print_header("Financials")

    assert "\x1b[" not in capsys.readouterr().out
