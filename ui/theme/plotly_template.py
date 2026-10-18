"""Synthwave Plotly template.

Registering this module (importing ``ui.theme``) makes every figure built
afterwards inherit the synthwave look: transparent background so the deep
night page shows through, mono font in cream, and the neon colorway.

The default template is ``plotly_dark+synthwave``: plotly_dark supplies the
dark-theme chrome (legend, tooltips) and synthwave overrides the colors and
the transparent background.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

#: Transparent so the page's deep-night background shows through.
TRANSPARENT = "rgba(0,0,0,0)"
#: Cyan grid at low opacity (design-system spec).
GRID_COLOR = "rgba(0,240,255,0.15)"
#: Neon cyan: the subject series (score radar, company P/E).
NEON_CYAN = "#00f0ff"
#: Neon pink: the synthwave counterpoint accent.
NEON_PINK = "#ff2d95"
#: Gold: intrinsic value (the DCF bars, matching the gold DCF chip).
GOLD = "#d4af37"
#: Chrome: the neutral reference bar (market price, peer median).
CHROME = "#c0c0d0"
#: Neon colorway: pink, cyan, purple, gold.
COLORWAY = [NEON_PINK, NEON_CYAN, "#9b4dff", GOLD]

synthwave = go.layout.Template()
synthwave.layout = dict(
    paper_bgcolor=TRANSPARENT,
    plot_bgcolor=TRANSPARENT,
    font=dict(family="JetBrains Mono, monospace", color="#f0e6d2"),
    colorway=COLORWAY,
    xaxis=dict(gridcolor=GRID_COLOR),
    yaxis=dict(gridcolor=GRID_COLOR),
)
pio.templates["synthwave"] = synthwave
pio.templates.default = "plotly_dark+synthwave"
