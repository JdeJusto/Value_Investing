from typing import Optional

from backend.analytics.calculator import MetricCalculator


class RevenueGrowthCalculator(MetricCalculator):
    def calculate(
        self,
        revenue_current: Optional[float] = None,
        revenue_prior: Optional[float] = None,
        **kwargs
    ) -> Optional[float]:
        if (
            revenue_current is not None
            and revenue_prior is not None
            and revenue_prior != 0
        ):
            return (revenue_current - revenue_prior) / revenue_prior
        return None
