from typing import Optional

from backend.analytics.calculator import MetricCalculator


class RoeCalculator(MetricCalculator):
    def calculate(
        self,
        net_income: float | None = None,
        equity: float | None = None,
        **kwargs
    ) -> float | None:
        if net_income is not None and equity is not None and equity != 0:
            return net_income / equity
        return None
