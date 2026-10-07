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


# --- rich builders (panels, headings, kv lines, tables) -------------------


def test_banner_contains_the_title_and_stays_capped():
    buffer = io.StringIO()
    console = get_console(no_color=True)
    console.file = buffer
    cli_output.print_banner("Comprehensive analysis: AAPL", console=console)
    out = buffer.getvalue()
    assert "Comprehensive analysis: AAPL" in out
    assert ESC not in out
    assert max(len(line) for line in out.splitlines()) <= cli_output.PANEL_WIDTH


def test_banner_without_body_is_exactly_two_border_lines():
    buffer = io.StringIO()
    console = get_console(no_color=True)
    console.file = buffer
    cli_output.print_banner("Header", console=console)
    lines = [line for line in buffer.getvalue().splitlines() if line]
    assert len(lines) == 2
    assert lines[0].startswith("╭") and lines[1].startswith("╰")


def test_print_panel_never_exceeds_the_panel_width():
    buffer = io.StringIO()
    console = get_console(no_color=True)
    console.file = buffer
    cli_output.print_panel(cli_output.section_panel("DCF", "body"), console=console)
    assert max(len(line) for line in buffer.getvalue().splitlines()) <= (
        cli_output.PANEL_WIDTH
    )


def test_heading_and_rule_layout():
    heading = cli_output.heading("1) Company overview", indent=0)
    assert str(heading) == "1) Company overview"
    assert heading.style == cli_output.HEADER
    rule = cli_output.rule(indent=2)
    assert str(rule) == "  " + "─" * 60
    assert rule.style == cli_output.MUTED


def test_kv_line_matches_the_classic_key_value_layout():
    line = cli_output.kv_line("Score", "—")
    assert str(line) == "  " + f"{'Score':>28}" + " : " + "—"
    left = cli_output.kv_line(
        "Price", "$1.00", key_width=6, indent="  ", align="left", sep=" "
    )
    assert str(left) == "  Price  $1.00"


def test_kv_line_preserves_value_styles_on_a_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _TTY())
    console = get_console()
    buffer = io.StringIO()
    console.file = buffer
    console.print(
        cli_output.kv_line("Confidence", confidence_text("HIGH")), soft_wrap=True
    )
    out = buffer.getvalue()
    assert "Confidence" in out and "HIGH" in out
    assert ESC in out


def test_print_kv_never_wraps_long_values(monkeypatch):
    monkeypatch.setattr(sys, "stdout", io.StringIO())  # non-TTY
    buffer = io.StringIO()
    console = get_console()
    console.file = buffer
    long_value = "word " * 60
    cli_output.print_kv([("Insight", long_value)], key_width=20, console=console)
    lines = [line for line in buffer.getvalue().splitlines() if line]
    assert len(lines) == 1
    assert long_value.strip() in lines[0]


def test_bullet_line_and_rule_line_marks():
    bullet = cli_output.bullet_line("Anomaly: marginal drop", style=cli_output.DANGER)
    assert str(bullet) == "  • Anomaly: marginal drop"
    deep = cli_output.bullet_line("Technology: 40%", indent="    ")
    assert str(deep) == "    • Technology: 40%"
    assert str(cli_output.rule_line("PASS", "criterion_1_size")) == (
        "  ✓ PASS  criterion_1_size"
    )
    assert str(cli_output.rule_line("FAIL", "criterion_2_pe")) == (
        "  ✗ FAIL  criterion_2_pe"
    )
    assert str(cli_output.rule_line("N/A", "criterion_3")) == "  · N/A  criterion_3"


def test_rule_line_is_colored_on_a_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _TTY())
    out = _render(get_console(), cli_output.rule_line("FAIL", "r1"))
    assert ESC in out
    assert "✗ FAIL" in out


def test_data_table_renders_cells_and_alignment():
    table = cli_output.data_table(
        [("fiscal_year", 1), ("fcf_yield", 1)],
        [["2025", "12.3%"]],
        title="Valuation",
    )
    assert str(table.title) == "Valuation"
    assert table.columns[0].justify == "right"
    out = _render(get_console(no_color=True), table)
    assert "fiscal_year" in out and "2025" in out and "12.3%" in out
    assert ESC not in out


def test_data_table_converts_ansi_cells_into_styles():
    """A colored cell must render clean when color is disabled."""
    table = cli_output.data_table([("Verdict", 0)], [["\x1b[92mBUY\x1b[0m"]])
    out = _render(get_console(no_color=True), table)
    assert "BUY" in out
    assert ESC not in out


# --- cli/formatters delegation -------------------------------------------


def test_print_header_renders_a_bordered_panel(capsys):
    from cli.formatters import print_header

    cli_output.reset_no_color()
    print_header("Fundamental analysis: AAPL")
    out = capsys.readouterr().out
    assert "Fundamental analysis: AAPL" in out
    assert "╭" in out and "╰" in out
    assert ESC not in out


def test_print_section_renders_title_and_rule(capsys):
    from cli.formatters import print_section

    cli_output.reset_no_color()
    print_section("Reasons")
    out = capsys.readouterr().out
    assert "Reasons" in out
    assert "─" * 20 in out
    assert ESC not in out


def test_print_key_value_keeps_the_classic_layout(capsys):
    from cli.formatters import print_key_value

    cli_output.reset_no_color()
    print_key_value("Score", "—")
    out = capsys.readouterr().out
    assert "Score : —" in out
    assert ESC not in out


def test_print_table_renders_headers_and_rows(capsys):
    from cli.formatters import print_table

    cli_output.reset_no_color()
    print_table([("Ticker", 0), ("Score", 1)], [["AAPL", "82.9"]], title="Ranking")
    out = capsys.readouterr().out
    assert "Ranking" in out and "Ticker" in out and "AAPL" in out and "82.9" in out
    assert ESC not in out


# --- spinners and progress bars ------------------------------------------


def test_status_is_silent_when_output_is_redirected(monkeypatch):
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    with cli_output.status("Screening 500 tickers..."):
        pass
    assert sys.stdout.getvalue() == ""


def test_status_animates_on_a_terminal(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _TTY())
    with cli_output.status("Screening 500 tickers..."):
        pass
    out = sys.stdout.getvalue()
    assert ESC in out
    assert "Screening 500 tickers..." in out


def test_status_can_be_disabled_explicitly(monkeypatch):
    monkeypatch.setattr(sys, "stdout", _TTY())
    with cli_output.status("Anything", enabled=False):
        pass
    assert sys.stdout.getvalue() == ""


def test_progress_is_silent_when_output_is_redirected(monkeypatch):
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    with cli_output.progress(3, "Analyzing") as bar:
        bar.advance()
        bar.update(3)
    assert sys.stdout.getvalue() == ""


def test_progress_renders_and_counts_the_batch_on_a_terminal(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _TTY())
    with cli_output.progress(2, "Analyzing") as bar:
        bar.advance()
        bar.advance()
    out = sys.stdout.getvalue()
    assert ESC in out
    assert "Analyzing" in out
    assert "2/2" in out


def test_progress_can_be_disabled_explicitly(capsys):
    with cli_output.progress(3, "Analyzing", enabled=False) as bar:
        bar.advance(2)
        bar.update(1)
        bar.set_total(5)
        bar.set_description("Analyzing AAPL")
    assert capsys.readouterr().out == ""


def test_progress_accepts_a_batch_size_known_only_later(monkeypatch):
    """The screener only learns the batch size from its first callback."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _TTY())
    with cli_output.progress(0, "Screening") as bar:
        bar.set_total(2)
        bar.set_description("Screening MSFT")
        bar.update(2)
    out = sys.stdout.getvalue()
    assert ESC in out
    assert "2/2" in out
