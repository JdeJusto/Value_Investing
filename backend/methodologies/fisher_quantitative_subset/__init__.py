"""``fisher_quantitative_subset`` — 4 of Fisher's 15 points (quantitative subset)."""

from backend.methodologies.fisher_quantitative_subset.methodology import (
    FisherQuantitativeSubsetMethodology,
)

METHODOLOGY = FisherQuantitativeSubsetMethodology()

__all__ = ["METHODOLOGY", "FisherQuantitativeSubsetMethodology"]
