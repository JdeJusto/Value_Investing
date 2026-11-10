"""Price context adapters for batch methodology evaluation.

Methodologies receive a small object exposing ``get_current_price``,
``get_market_cap`` and ``get_beta`` (see ``backend.valuation.dcf``). In
single-company flows that object is the real :class:`PriceService`; in batch
flows the numbers were already fetched in bulk, so this module provides a
plain value object with the same surface.

``beta=None`` is intentional and safe: the DCF falls back to a beta of 1.0
when the market beta is unavailable, so a batch context always lets the
valuation run instead of degrading the rule to ``N/A``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatchPriceContext:
    """One ticker's price inputs, pre-fetched for a batch evaluation."""

    price: float | None
    market_cap: float | None = None
    beta: float | None = None

    def get_current_price(self, _ticker: str) -> float | None:
        return self.price

    def get_market_cap(self, _ticker: str) -> float | None:
        return self.market_cap

    def get_beta(self, _ticker: str) -> float | None:
        return self.beta
