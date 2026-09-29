"""Lynch GARP methodology (registered automatically by the registry)."""

from backend.methodologies.lynch_garp.methodology import LynchGARPMethodology

METHODOLOGY = LynchGARPMethodology()

__all__ = ["METHODOLOGY", "LynchGARPMethodology"]