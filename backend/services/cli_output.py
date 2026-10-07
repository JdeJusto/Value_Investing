"""Shared Rich rendering helpers for the CLI.

Every command renders through this module so that ``--no-color``,
``NO_COLOR`` (https://no-color.org/) and non-TTY redirection are honored in
a single place. Commands must never build their own ``Console``: they call
:func:`get_console` and the builders below.

Color is emitted only when all three conditions hold:

1. ``--no-color`` was not passed (the CLI root stores the flag with
   :func:`set_no_color` before dispatching the command),
2. ``NO_COLOR`` is absent from the environment,
3. ``sys.stdout`` is a TTY — pipes and redirects always get plain text.

Rich markup is deliberately disabled on the console: financial text often
contains brackets (``P/E [ttm]``, ``Risk [high]``) that Rich would parse as
style tags and silently drop, changing the data shown. Styling therefore
goes through :class:`rich.text.Text` objects built by the helpers below,
which survive intact in any output mode.

The palette mirrors the logo: navy-family structure, green for positive
signals, red for negative ones.
"""

from __future__ import annotations

import math
import os
import sys
from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

# Palette (logo navy + green).
PRIMARY = "bright_cyan"  # structure: headers, panel borders
ACCENT = "bright_green"  # positive: BUY, gains, checks
DANGER = "bright_red"  # negative: AVOID, losses, critical
WARNING = "yellow"  # caution: WATCH, warnings
MUTED = "dim"  # secondary: N/A, notes
HEADER = "bold white"  # table headers and titles

# Verdict -> color mapping.
VERDICT_COLORS = {
    "BUY": "bright_green",
    "WATCH": "yellow",
    "HOLD": "cyan",
    "AVOID": "bright_red",
    "INSUFFICIENT_DATA": "dim",
}

CONFIDENCE_COLORS = {
    "HIGH": "bright_green",
    "MEDIUM": "yellow",
    "LOW": "red",
}

SEVERITY_COLORS = {
    "INFO": "cyan",
    "WARNING": "yellow",
    "CRITICAL": "bright_red",
}

# Piped output has no terminal width; Rich would fall back to 80 columns and
# fold wide table cells over several lines. 160 keeps every cell on one line.
PIPE_WIDTH = 160

# Panels always fill the console width, so they are capped: a piped report
# must not draw a 160-column banner around a two-line header.
PANEL_WIDTH = 100

_NO_COLOR = False


def set_no_color(value: bool) -> None:
    """Store the CLI root's ``--no-color`` flag for this invocation."""
    global _NO_COLOR
    _NO_COLOR = bool(value)


def reset_no_color() -> None:
    """Clear the stored flag (tests and long-lived callers)."""
    set_no_color(False)


def color_enabled(no_color: bool = False) -> bool:
    """Whether colored output should be emitted right now.

    ``no_color=True`` disables color for one call; otherwise the flag stored
    by :func:`set_no_color` applies. ``NO_COLOR`` and a non-TTY stdout always
    win over the flag.
    """
    if _NO_COLOR or no_color:
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    return bool(sys.stdout.isatty())


def get_console(no_color: bool = False) -> Console:
    """Return a Console configured for the current output context.

    Disables color when ``--no-color`` is set, when ``NO_COLOR`` is present
    or when stdout is not a TTY. Markup and highlighting stay off so data
    strings are never rewritten.
    """
    disabled = not color_enabled(no_color)
    kwargs: dict = {
        "no_color": disabled,
        "force_terminal": not disabled,
        "markup": False,
        "highlight": False,
    }
    if disabled and not sys.stdout.isatty():
        kwargs["width"] = PIPE_WIDTH
    return Console(**kwargs)


def verdict_text(verdict: str) -> Text:
    """Verdict rendered in its palette color (unstyled when unknown)."""
    value = verdict or ""
    return Text(value, style=VERDICT_COLORS.get(value, ""))


def confidence_text(confidence: str) -> Text:
    """Confidence level rendered in its palette color."""
    value = confidence or ""
    return Text(value, style=CONFIDENCE_COLORS.get(value, ""))


def severity_text(severity: str) -> Text:
    """Alert severity rendered in its palette color."""
    value = severity or ""
    return Text(value, style=SEVERITY_COLORS.get(value, ""))


def metric_table(title: str) -> Table:
    """A titled table ready for metric rows (labels left, values right)."""
    table = Table(title=title, title_style=PRIMARY, header_style=HEADER)
    table.add_column("Metric", style=HEADER)
    table.add_column("Value", justify="right")
    return table


def section_panel(title: str, body) -> Panel:
    """A bordered panel with a left-aligned title in the primary color."""
    return Panel(body, title=title, title_align="left", border_style=PRIMARY)


class _EmptyBody:
    """Renders nothing, so a banner panel is exactly two border lines."""

    def __rich_console__(self, console, options):
        return iter(())


def print_banner(title: str, body=None, *, console: Console | None = None) -> None:
    """Print the command banner: a bordered panel titled with ``title``.

    ``body`` is optional supporting text (facts, subtitles); without it the
    panel is a two-line banner.
    """
    console = console or get_console()
    panel = Panel(
        body if body is not None else _EmptyBody(),
        title=Text(title, style=HEADER),
        border_style=PRIMARY,
        padding=(0, 1),
    )
    console.print()
    print_panel(panel, console=console)


def print_panel(renderable, *, console: Console | None = None) -> None:
    """Print a panel capped at :data:`PANEL_WIDTH` (never wider than needed)."""
    console = console or get_console()
    console.print(renderable, width=min(console.width, PANEL_WIDTH))


def heading(text: str, indent: int = 2) -> Text:
    """Section heading (bold white) as used before a block of metrics."""
    return Text(" " * indent + text, style=HEADER)


def rule(length: int = 60, char: str = "─", indent: int = 2) -> Text:
    """Dim horizontal rule, the companion line under a :func:`heading`."""
    return Text(" " * indent + char * length, style=MUTED)


def kv_line(
    label: str,
    value,
    key_width: int = 28,
    indent: str = "  ",
    align: str = "right",
    sep: str = " : ",
) -> Text:
    """One aligned label/value line.

    ``align="right"`` with ``sep=" : "`` reproduces the classic
    ``print_key_value`` layout; sections use left alignment with a plain
    separator. ``value`` may be a :class:`Text` to keep its styling.
    """
    padded = f"{label:>{key_width}}" if align == "right" else f"{label:<{key_width}}"
    line = Text(f"{indent}{padded}{sep}")
    line.append(value if isinstance(value, Text) else str(value))
    return line


def print_kv(
    pairs,
    key_width: int = 20,
    indent: str = "     ",
    align: str = "left",
    sep: str = " ",
    *,
    console: Console | None = None,
) -> None:
    """Print aligned label/value pairs, one per line (never wrapped)."""
    console = console or get_console()
    for label, value in pairs:
        console.print(
            kv_line(label, value, key_width, indent, align, sep), soft_wrap=True
        )


def bullet_line(
    text, style: str = MUTED, marker: str = "•", indent: str = "  "
) -> Text:
    """``indent`` + ``marker`` in ``style`` + text — alerts and lists."""
    line = Text(indent)
    line.append(f"{marker} ", style=style)
    line.append(text if isinstance(text, Text) else str(text))
    return line


def rule_line(status: str, rule_id: str, indent: str = "  ") -> Text:
    """``  ✓ PASS  <rule id>`` — one evaluated methodology criterion."""
    mark, style = {
        "PASS": ("✓", ACCENT),
        "FAIL": ("✗", DANGER),
        "N/A": ("·", MUTED),
    }.get(status, ("·", MUTED))
    line = Text(indent)
    line.append(f"{mark} {status}", style=style)
    line.append(f"  {rule_id}")
    return line


class _NullProgress:
    """Progress stand-in for redirected output: same API, no rendering."""

    def advance(self, n: int = 1) -> None:
        """Ignore the step (nothing is drawn outside a terminal)."""

    def update(self, completed: int) -> None:
        """Ignore the absolute position (nothing is drawn)."""

    def set_total(self, total: int) -> None:
        """Ignore the batch size (nothing is drawn)."""

    def set_description(self, description: str) -> None:
        """Ignore the caption (nothing is drawn)."""


@contextmanager
def status(
    message: str, *, console: Console | None = None, enabled: bool | None = None
):
    """Live spinner while a long operation runs.

    Spinners animate with cursor control, so they only start on a terminal;
    redirected output must stay free of escape codes. Reserve this for steps
    that reliably take over a second — a spinner on a fast command just adds
    noise.
    """
    if enabled is None:
        enabled = sys.stdout.isatty()
    if not enabled:
        yield
        return
    console = console or get_console()
    with console.status(message, spinner="dots", spinner_style=PRIMARY):
        yield


@contextmanager
def progress(
    total: int,
    description: str = "",
    *,
    console: Console | None = None,
    enabled: bool | None = None,
):
    """Progress bar for a batch of items; a no-op object when redirected.

    Yields an object with ``advance(n=1)``, ``update(completed)``,
    ``set_total(total)`` and ``set_description(text)``, so callers can run
    the same loop on and off a terminal. Pass ``total=0`` when the batch
    size is only known once the loop is running and set it with
    ``set_total``::

        with progress(len(tickers), "Analyzing") as bar:
            for ticker in tickers:
                ...
                bar.advance()
    """
    if enabled is None:
        enabled = sys.stdout.isatty()
    if not enabled:
        yield _NullProgress()
        return
    console = console or get_console()
    bar = Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    )
    with bar:
        task = bar.add_task(description, total=total if total > 0 else None)

        class _Batch:
            def advance(self, n: int = 1) -> None:
                bar.advance(task, n)

            def update(self, completed: int) -> None:
                bar.update(task, completed=completed)

            def set_total(self, total: int) -> None:
                bar.update(task, total=total)

            def set_description(self, description: str) -> None:
                bar.update(task, description=description)

        yield _Batch()


def data_table(
    headers: list[tuple[str, int]],
    rows: list[list],
    title: str | None = None,
    padding: int = 2,
) -> Table:
    """Rich table from ``(label, align)`` columns (align 1 = right).

    Cells may be plain strings, raw-ANSI strings (parsed into styles, so
    colored cells keep their width) or :class:`Text` objects.
    """
    del padding  # Rich sizes columns itself; kept for signature parity.
    table = Table(title=title, title_style=PRIMARY, header_style=HEADER)
    for label, align in headers:
        table.add_column(label, justify="right" if align else "left")
    for row in rows:
        cells = []
        for cell in row:
            if isinstance(cell, Text) or not isinstance(cell, str):
                cells.append(cell)
            elif "\x1b" in cell:
                cells.append(Text.from_ansi(cell))
            else:
                cells.append(cell)
        table.add_row(*cells)
    return table


def format_currency(value: float | None, decimals: int = 2) -> str:
    """$1.2B / $3.4M / $1.2K style currency, or ``N/A`` when unavailable."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "N/A"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.{decimals}f}"


def format_pct(value: float | None, decimals: int = 1) -> str:
    """Percentage of a 0-1 fraction, or ``N/A`` when unavailable."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "N/A"
    return f"{value * 100:.{decimals}f}%"
