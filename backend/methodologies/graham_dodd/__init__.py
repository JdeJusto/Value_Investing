"""Graham & Dodd methodology.

Benjamin Graham & David Dodd, *Security Analysis* (1934). Detects deep
value from balance-sheet signatures: NWC test, fixed-charge coverage,
earnings stability, balance sheet strength, and margin of safety.

Coexists with graham (The Intelligent Investor) and buffett_clark.
"""

from .methodology import GrahamDoddMethodology

METHODOLOGY = GrahamDoddMethodology()

__all__ = ["GrahamDoddMethodology", "METHODOLOGY"]
