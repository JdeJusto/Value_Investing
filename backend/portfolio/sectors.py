"""Canonical sector labels for the portfolio views.

Financial-DataBase stores the Yahoo Finance sector taxonomy (``Consumer
Defensive``, ``Consumer Cyclical``, ``Technology``...). The portfolio uses the
GICS labels most users expect (``Consumer Staples``, ``Consumer
Discretionary``, ``Information Technology``). Unknown values are returned
unchanged; callers fall back to ``Unknown``.
"""

from __future__ import annotations

#: Yahoo Finance sector -> GICS label.
_SECTOR_LABELS = {
    "basic materials": "Materials",
    "communication services": "Communication Services",
    "consumer cyclical": "Consumer Discretionary",
    "consumer defensive": "Consumer Staples",
    "energy": "Energy",
    "financial services": "Financials",
    "healthcare": "Health Care",
    "industrials": "Industrials",
    "real estate": "Real Estate",
    "technology": "Information Technology",
    "utilities": "Utilities",
}


def canonical_sector(value: str | None) -> str | None:
    """Map a stored sector to its GICS label (``None`` stays ``None``)."""
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    return _SECTOR_LABELS.get(cleaned.lower(), cleaned)
