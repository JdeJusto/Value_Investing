"""Graham defensive-investor methodology.

Registers :class:`GrahamMethodology` as ``METHODOLOGY`` so the registry
discovers it automatically.
"""

from __future__ import annotations

from backend.methodologies.graham.methodology import GrahamMethodology

METHODOLOGY = GrahamMethodology()

__all__ = ["METHODOLOGY", "GrahamMethodology"]
