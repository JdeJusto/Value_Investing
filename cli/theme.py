"""Synthwave ANSI palette for opt-in CLI commands.

The module is intentionally opt-in: existing commands keep their current
Rich palette. New commands import :mod:`cli.theme` for a neon header band,
verdict colors and highlighted big numbers.

Color is emitted only when :func:`backend.services.cli_output.color_enabled`
allows it, so the global ``--no-color`` flag, ``NO_COLOR`` and non-TTY
stdout (pipes/CI) are honored automatically.
"""

from __future__ import annotations

from backend.services import cli_output

NEON_PINK = "\033[38;5;205m"
NEON_CYAN = "\033[38;5;51m"
NEON_PURPLE = "\033[38;5;141m"
GOLD = "\033[38;5;220m"
CHROME = "\033[38;5;252m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

HEADER_WIDTH = 72

_VERDICT_COLORS = {
    "BUY": NEON_CYAN,
    "WATCH": GOLD,
    "HOLD": NEON_PURPLE,
    "AVOID": NEON_PINK,
}


def disable() -> None:
    """Disable color for the current invocation (used by ``--no-color``)."""
    cli_output.set_no_color(True)


def is_enabled() -> bool:
    """True when ANSI output is currently allowed."""
    return cli_output.color_enabled()


def _wrap(text: str, *codes: str) -> str:
    if not is_enabled():
        return text
    return "".join(codes) + text + RESET


def neon_cyan(text: str) -> str:
    return _wrap(text, NEON_CYAN)


def gold(text: str) -> str:
    return _wrap(text, GOLD)


def dim(text: str) -> str:
    return _wrap(text, DIM)


def big_number(text: str) -> str:
    return _wrap(text, BOLD, GOLD)


def bold(text: str) -> str:
    """Bold without changing the color (numbers stay uncolored)."""
    return _wrap(text, BOLD)


def section_header(text: str) -> str:
    """Cyan bold section header for the hierarchical T-view."""
    return _wrap(text.upper(), NEON_CYAN, BOLD)


def section_rule(text: str) -> str:
    """Dim underline matching a section header width."""
    return _wrap("─" * min(len(text) + 4, 40), DIM)


def print_section_header(text: str) -> None:
    """Print a T-view section header with a blank line and underline."""
    print()
    print(section_header(text))
    print(section_rule(text))


def color_big_number(text: str) -> str:
    """Alias for :func:`big_number` (the public theme API)."""
    return big_number(text)


def color_verdict(verdict: str) -> str:
    """Color one verdict; identity for HOLD-free/unknown values."""
    value = getattr(verdict, "value", verdict)
    code = _VERDICT_COLORS.get(str(value).upper())
    return _wrap(str(value), code) if code else str(value)


def print_header(title: str, subtitle: str = "") -> None:
    """Print a cyan header band, with an optional subtitle line."""
    title = str(title)
    rule_width = max(1, HEADER_WIDTH - len(title) - 3)
    print()
    print(neon_cyan(f"╭─ {title} " + "─" * rule_width))
    if subtitle:
        print(neon_cyan("│ ") + subtitle)
    print(neon_cyan("╰" + "─" * (HEADER_WIDTH - 1)))
