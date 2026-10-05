"""Tiny display helpers shared by the UI adapters.

Pure move out of ``ui_adapter`` so ``portfolio_adapter`` can format values
without importing the general adapter (which would create an import cycle).
"""

from __future__ import annotations

from typing import Any

DASH = "—"


def fmt_or_dash(value: Any, digits: int = 2, percent: bool = False) -> str:
    """Format a number for display; ``None`` becomes an em dash, never 0."""
    if value is None:
        return DASH
    if percent:
        return f"{value:.{digits}%}"
    return f"{value:,.{digits}f}"
