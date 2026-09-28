"""Buffett/Clark methodology.

Mary Buffett & David Clark, *Warren Buffett and the Interpretation of
Financial Statements* (2001). Detects durable competitive advantage (DCA)
from financial-statement signatures: gross margin level and durability,
interest burden, debt, cash, capex, retained earnings.

Both coexist with the existing ``backend/intelligence/buffett.py`` module
(qualitative 4-pillar filter). See ``README.md`` for the distinction.
"""

from .methodology import BuffettClarkMethodology

METHODOLOGY = BuffettClarkMethodology()

__all__ = ["BuffettClarkMethodology", "METHODOLOGY"]
