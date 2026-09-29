from typing import Optional

from backend.analytics.calculator import MetricCalculator


class RevenueGrowthCalculator(MetricCalculator):
    def calculate(
        self,
        revenue_current: float | None = None,
        revenue_prior: float | None = None,
        **kwargs
    ) -> float | None:
        if (
            revenue_current is not None
            and revenue_prior is not None
            and revenue_prior != 0
        ):
            return (revenue_current - revenue_prior) / revenue_prior
        return None
