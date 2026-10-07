"""Unit tests for the shared Rich CLI output module (``cli_output``).

They cover the three color rules (``--no-color``, ``NO_COLOR``, non-TTY
stdout), the helper builders and the flag plumbing done in ``cli/main.py``.
Every test that depends on TTY-ness forces it explicitly, so the suite is
independent of the environment it runs in.
"""

from __future__ import annotations

import io
import sys

import pytest
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from backend.services import cli_output
from backend.services.cli_output import (
    confidence_text,
    format_currency,
    format_pct,
    get_console,
    metric_table,
    section_panel,
    severity_text,
    verdict_text,
)
from cli.main import main

ESC = "\x1b"


class _TTY(io.StringIO):
    """A stdout stand-in that claims to be a terminal."""

    def isatty(self) -> bool:  # pragma: no cover - trivial
        return True


@pytest.fixture(autouse=True)
def _clean_no_color_flag():
    """Never leak the module flag from one test into the next."""
    cli_output.reset_no_color()
    yield
    cli_output.reset_no_color()


def _render(console, renderable) -> str:
    """Print ``renderable`` through ``console`` and return the raw output."""
    buffer = io.StringIO()
    console.file = buffer
    console.print(renderable)
    return buffer.getvalue()


# --- color rules -----------------------------------------------------------


def test_get_console_no_color_emits_no_ansi():
    out = _render(get_console(no_color=True), Text("BUY", style="bright_green"))
    assert ESC not in out
    assert "BUY" in out


def test_non_tty_stdout_emits_no_ansi(monkeypatch):
    monkeypatch.setattr(sys, "stdout", io.StringIO())  # isatty() is False
    out = _render(get_console(), Text("BUY", style="bright_green"))
    assert ESC not in out
    assert "BUY" in out


def test_no_color_env_var_beats_a_tty(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(sys, "stdout", _TTY())
    out = _render(get_console(), Text("SELL", style="bold red"))
    assert ESC not in out
    assert "SELL" in out


def test_tty_without_flags_keeps_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _TTY())
    out = _render(get_console(), Text("BUY", style="bright_green"))
    assert ESC in out


def test_console_never_rewrites_bracketed_data():
    """Rich markup is off: ``[ttm]`` must survive, not vanish as a tag."""
    out = _render(get_console(no_color=True), "P/E [ttm] and Risk [high]")
    assert "P/E [ttm] and Risk [high]" in out


def test_piped_console_uses_a_generous_width(monkeypatch):
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert get_console().width == cli_output.PIPE_WIDTH


# --- helper builders -------------------------------------------------------


def test_verdict_text_buy_is_green():
    text = verdict_text("BUY")
    assert isinstance(text, Text)
    assert str(text) == "BUY"
    assert text.style == "bright_green"


def test_verdict_text_unknown_is_unstyled():
    assert verdict_text("WAT").style in ("", None)


def test_confidence_and_severity_use_their_palettes():
    assert confidence_text("HIGH").style == "bright_green"
    assert confidence_text("LOW").style == "red"
    assert severity_text("CRITICAL").style == "bright_red"
    assert str(severity_text("INFO")) == "INFO"


def test_metric_table_carries_its_title():
    table = metric_table("Title")
    assert isinstance(table, Table)
    assert str(table.title) == "Title"


def test_section_panel_is_a_panel_with_the_title():
    panel = section_panel("Overview", "body")
    assert isinstance(panel, Panel)
    assert "Overview" in str(panel.title)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "N/A"),
        (float("nan"), "N/A"),
        (1_200_000_000, "$1.2B"),
        (3_400_000, "$3.4M"),
        (1_200, "$1.2K"),
        (12.34, "$12.34"),
    ],
)
def test_format_currency(value, expected):
    assert format_currency(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "N/A"), (0.1234, "12.3%"), (-0.045, "-4.5%")],
)
def test_format_pct(value, expected):
    assert format_pct(value) == expected


# --- formatters honor the same rules --------------------------------------


def test_formatters_stay_plain_without_a_tty(monkeypatch):
    from cli.formatters import green, red

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert green("up") == "up"
    assert red("down") == "down"


def test_formatters_color_on_a_tty(monkeypatch):
    from cli.formatters import green

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _TTY())
    assert ESC in green("up")


def test_formatters_respect_no_color_flag(monkeypatch):
    from cli.formatters import green

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _TTY())
    cli_output.set_no_color(True)
    assert green("up") == "up"


# --- --no-color plumbing in cli/main.py -----------------------------------


def _run_main(monkeypatch, *argv) -> str:
    """Run the CLI against a forced TTY and return everything it printed."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    buffer = _TTY()
    monkeypatch.setattr(sys, "stdout", buffer)
    monkeypatch.setattr(sys, "argv", ["main.py", *argv])
    main()
    return buffer.getvalue()


def test_flag_before_the_command_disables_color(monkeypatch):
    out = _run_main(monkeypatch, "--no-color", "methodologies", "list")
    assert "Registered methodologies" in out
    assert ESC not in out


def test_flag_after_a_nested_subcommand_disables_color(monkeypatch):
    out = _run_main(monkeypatch, "methodologies", "list", "--no-color")
    assert "Registered methodologies" in out
    assert ESC not in out


def test_without_the_flag_a_tty_stays_colored(monkeypatch):
    """Companion to the two tests above: color is on unless the flag is used."""
    out = _run_main(monkeypatch, "methodologies", "list")
    assert "Registered methodologies" in out
    assert ESC in out


def test_flag_is_reset_between_invocations(monkeypatch):
    _run_main(monkeypatch, "--no-color", "methodologies", "list")
    # A later invocation without the flag must start from a clean slate.
    out = _run_main(monkeypatch, "methodologies", "list")
    assert ESC in out
