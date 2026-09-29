
from backend.analytics.calculator import MetricCalculator


class PerCalculator(MetricCalculator):
    def calculate(
        self,
        market_cap: float | None = None,
        net_income: float | None = None,
        **kwargs
    ) -> float | None:
        if market_cap is not None and net_income is not None and net_income != 0:
            return market_cap / net_income
        return None
