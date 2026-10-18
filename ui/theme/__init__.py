"""Synthwave-yuppie theme: CSS injection, header band, palette, Plotly template.

Importing this package registers the ``synthwave`` Plotly template (see
``plotly_template``) so every figure built afterwards inherits the neon
palette and the transparent background. Call ``inject_theme()`` once per
page run to inject the CSS, then use ``header()`` for the page band.

Re-theming the whole app means changing only this package.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

import streamlit as st

from ui.theme import plotly_template as _plotly_template  # noqa: F401

_CSS = (Path(__file__).parent / "style.css").read_text(encoding="utf-8")

#: Palette (mirrors style.css :root and docs/ui_design_system.md).
PALETTE = {
    "bg": "#0a0a1a",
    "surface": "#14142b",
    "neon_pink": "#ff2d95",
    "neon_cyan": "#00f0ff",
    "neon_purple": "#9b4dff",
    "gold": "#d4af37",
    "cream": "#f0e6d2",
    "chrome": "#c0c0d0",
    "dim": "#4a4a6a",
}

#: Semantic verdict colors (design-system mapping).
VERDICT_COLORS = {
    "BUY": PALETTE["neon_cyan"],
    "WATCH": PALETTE["gold"],
    "HOLD": PALETTE["neon_purple"],
    "AVOID": PALETTE["neon_pink"],
    "INSUFFICIENT": PALETTE["dim"],
    "INSUFFICIENT_DATA": PALETTE["dim"],
    "N/A": PALETTE["dim"],
}

#: Alert severity colors (CRITICAL = neon-pink, WARNING = gold, INFO = cyan).
SEVERITY_COLORS = {
    "CRITICAL": PALETTE["neon_pink"],
    "WARNING": PALETTE["gold"],
    "INFO": PALETTE["neon_cyan"],
}


def inject_theme() -> None:
    """Inject the synthwave CSS once per page run (idempotent)."""
    if st.session_state.get("_vi_theme_injected"):
        return
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
    st.session_state["_vi_theme_injected"] = True


def header(ticker: str, subtitle: str = "") -> None:
    """Render the synthwave header band. Use from every page."""
    sub = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="vi-header"><h1>{escape(ticker)}</h1>{sub}</div>',
        unsafe_allow_html=True,
    )
