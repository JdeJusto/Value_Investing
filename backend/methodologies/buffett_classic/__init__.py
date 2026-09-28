"""buffett_classic — the existing Buffett/Munger 4-pillar filter, wrapped as a methodology.

The wrapper delegates to ``backend/intelligence/buffett_engine.py``; it does not
re-implement anything. See ``README.md`` for the distinction from ``buffett_clark``.
"""

from __future__ import annotations

from backend.methodologies.buffett_classic.methodology import (
    BuffettClassicMethodology,
)

METHODOLOGY = BuffettClassicMethodology()

__all__ = ["METHODOLOGY", "BuffettClassicMethodology"]
