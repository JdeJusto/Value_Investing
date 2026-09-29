"""Valuation modules that are explicitly NOT book-derived methodologies.

``backend/valuation/`` answers "what is this company actually worth?" for
compounders the five canon methodologies reject because their source books
predate modern growth-company economics. Nothing here is registered in
``backend.methodologies`` and nothing here feeds ``compare-methodologies``.
"""

from backend.valuation.base import SOURCE, DCFAssumptions, DCFResult
from backend.valuation.dcf import DCFValuation

__all__ = ["SOURCE", "DCFAssumptions", "DCFResult", "DCFValuation"]
