from typing import Optional

from backend.analytics.calculator import MetricCalculator


class PerCalculator(MetricCalculator):
    def calculate(self, market_cap: Optional[float] = None, net_income: Optional[float] = None, **kwargs) -> Optional[float]:
        if market_cap is not None and net_income is not None and net_income != 0:
            return market_cap / net_income
        return None
