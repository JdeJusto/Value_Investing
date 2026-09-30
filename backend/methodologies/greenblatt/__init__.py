"""``greenblatt`` — Magic Formula rankings (The Little Book That Beats the Market)."""

from backend.methodologies.greenblatt.methodology import GreenblattMethodology

METHODOLOGY = GreenblattMethodology()

__all__ = ["METHODOLOGY", "GreenblattMethodology"]
