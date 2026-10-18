"""Unit tests for the synthwave-yuppie theme module (``ui.theme``).

Pure checks: CSS contract, palette contrast (WCAG AA), and the Plotly
template registration. The idempotency test runs a tiny script under AppTest.
"""

from __future__ import annotations

import re
from pathlib import Path

from streamlit.testing.v1 import AppTest

_THEME_DIR = Path(__file__).resolve().parents[2] / "ui" / "theme"
_CSS_TEXT = (_THEME_DIR / "style.css").read_text(encoding="utf-8")


# --- WCAG contrast helpers (pure, no network) -------------------------------

def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance for a #rrggbb color."""
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    r, g, b = linear
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two colors (1.0 - 21.0)."""
    lum_fg = _relative_luminance(fg)
    lum_bg = _relative_luminance(bg)
    lighter, darker = max(lum_fg, lum_bg), min(lum_fg, lum_bg)
    return (lighter + 0.05) / (darker + 0.05)


# --- inject_theme ------------------------------------------------------------

def test_inject_theme_is_idempotent():
    """Calling inject_theme twice injects the CSS only once."""
    at = AppTest.from_string(
        "from ui.theme import inject_theme\n"
        "inject_theme()\n"
        "inject_theme()\n"
    )
    at.run()
    assert not at.exception, at.exception
    # Only one <style> block carries our :root palette marker.
    styles = [m.value for m in at.markdown if m.value and ":root" in m.value]
    assert len(styles) == 1, f"expected 1 injected style, got {len(styles)}"


def test_css_has_no_important():
    """The CSS avoids !important so it never fights Streamlit's own styles."""
    assert "!important" not in _CSS_TEXT


def test_css_defines_the_palette_and_contract_classes():
    """The design-system variables and the .vi-* contract classes exist."""
    for token in (
        "--vi-bg",
        "--vi-surface",
        "--vi-neon-pink",
        "--vi-neon-cyan",
        "--vi-neon-purple",
        "--vi-gold",
        "--vi-cream",
        "--vi-chrome",
    ):
        assert token in _CSS_TEXT, f"missing {token}"
    for css_class in ("vi-header", "vi-card", "vi-big-number", "vi-chip"):
        assert f".{css_class}" in _CSS_TEXT, f"missing .{css_class}"


# --- Plotly template ---------------------------------------------------------

def test_plotly_template_registered_as_synthwave():
    import plotly.io as pio

    import ui.theme  # noqa: F401 — importing registers the template

    assert "synthwave" in pio.templates


def test_new_figures_inherit_the_synthwave_template():
    """A figure built after ``import ui.theme`` carries the template."""
    import plotly.graph_objects as go

    import ui.theme  # noqa: F401 — importing sets the default template

    layout = go.Figure(go.Bar(x=["a"], y=[1])).layout.template.layout
    assert layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert "JetBrains Mono" in (layout.font.family or "")


def test_plotly_palette_constants_match_the_theme_palette():
    """The chart-trace constants mirror ``PALETTE`` (single source of truth)."""
    from ui.theme import PALETTE
    from ui.theme.plotly_template import CHROME, GOLD, NEON_CYAN, NEON_PINK

    assert NEON_CYAN == PALETTE["neon_cyan"]
    assert NEON_PINK == PALETTE["neon_pink"]
    assert GOLD == PALETTE["gold"]
    assert CHROME == PALETTE["chrome"]


def test_charts_hardcode_no_colors_outside_the_theme():
    """``ui/charts.py`` takes every trace color from the theme module."""
    charts_source = (_THEME_DIR.parent / "charts.py").read_text(encoding="utf-8")
    assert re.search(r"#[0-9a-fA-F]{6}", charts_source) is None


# --- Palette contrast (WCAG AA) ---------------------------------------------

def test_cream_on_bg_passes_wcag_aa():
    from ui.theme import PALETTE

    assert _contrast_ratio(PALETTE["cream"], PALETTE["bg"]) >= 4.5


def test_cream_on_surface_passes_wcag_aa():
    from ui.theme import PALETTE

    assert _contrast_ratio(PALETTE["cream"], PALETTE["surface"]) >= 4.5
