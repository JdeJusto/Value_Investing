"""Current ratio = current assets / current liabilities."""

from __future__ import annotations

from backend.analytics.calculator import MetricCalculator


class CurrentRatioCalculator(MetricCalculator):
    """Liquidity ratio; ``None`` when either side is unavailable or zero."""

    def calculate(
        self,
        current_assets: float | None = None,
        current_liabilities: float | None = None,
        **kwargs,
    ) -> float | None:
        if current_assets is None or current_liabilities is None:
            return None
        if current_liabilities == 0:
            return None
        return float(current_assets) / float(current_liabilities)
