# UI design system — synthwave-yuppie

## Direction
Synthwave (neon, deep night, gradient sunsets, chrome, perspective
grids) + 1980s yuppie investor (gold, marble, bold serif, Wall
Street). References: Miami Vice palette, GTA Vice City UI, chrome-
on-marble 80s annual reports, VHS overlays.

## Palette
--vi-bg: #0a0a1a
--vi-surface: #14142b
--vi-neon-pink: #ff2d95
--vi-neon-cyan: #00f0ff
--vi-neon-purple: #9b4dff
--vi-gold: #d4af37
--vi-cream: #f0e6d2
--vi-chrome: #c0c0d0

Semantic mapping:
- BUY → neon-cyan
- WATCH → gold
- HOLD → neon-purple
- AVOID → neon-pink
- INSUFFICIENT → dim gray (#4a4a6a)

## Typography
- Headings: Playfair Display (bold serif, 80s annual reports)
- Body and numbers: JetBrains Mono
- Big scores only: chrome gradient treatment, no other text

## Layout
- Header band: gradient background + subtle perspective grid.
- Cards: surface color, 1px neon border, hover raises with shadow.
- Tables: mono font, zebra rows, gold underline on headers.
- Plotly: transparent background, neon palette, cyan grid at low
  opacity, mono font.

## Interactivity
- Radar: preserve from Phase 4.
- Hover tooltips on all charts.
- One spotlight: big chrome number for overall verdict, subtle
  pulse via CSS keyframes (only there).
- Dimension filters on the Scorecard radar.

## What NOT to do
- No gradients on tables.
- No neon text > 14px except the big score numbers.
- No animation on tables.
- No fonts beyond Google Fonts (Playfair Display + JetBrains Mono).
- No JS beyond what Streamlit ships.

## Acceptance
- All pages render with the new theme.
- WCAG AA on body text (verified with a contrast formula test).
- Charts use the neon palette.
- Re-theming requires changing only `ui/theme/`.
