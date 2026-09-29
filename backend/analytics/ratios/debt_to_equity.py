from typing import Optional

from backend.analytics.calculator import MetricCalculator


class DebtToEquityCalculator(MetricCalculator):
    def calculate(
        self,
        total_debt: float | None = None,
        equity: float | None = None,
        **kwargs
    ) -> float | None:
        if total_debt is not None and equity is not None and equity != 0:
            return total_debt / equity
        return None
