from typing import Optional

from backend.analytics.calculator import MetricCalculator


class DebtToEquityCalculator(MetricCalculator):
    def calculate(
        self,
        total_debt: Optional[float] = None,
        equity: Optional[float] = None,
        **kwargs
    ) -> Optional[float]:
        if total_debt is not None and equity is not None and equity != 0:
            return total_debt / equity
        return None
