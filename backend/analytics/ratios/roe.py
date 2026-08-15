from typing import Optional

from backend.analytics.calculator import MetricCalculator


class RoeCalculator(MetricCalculator):
    def calculate(
        self,
        net_income: Optional[float] = None,
        equity: Optional[float] = None,
        **kwargs
    ) -> Optional[float]:
        if net_income is not None and equity is not None and equity != 0:
            return net_income / equity
        return None
