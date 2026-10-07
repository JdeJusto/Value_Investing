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

from rich.console import Console
from rich.panel import Panel
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
