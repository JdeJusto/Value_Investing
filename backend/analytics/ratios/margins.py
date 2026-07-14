from typing import Optional

import numpy as np

from backend.analytics.calculator import MetricCalculator


class OperatingMarginCalculator(MetricCalculator):
    def calculate(self, operating_income: Optional[float] = None, revenue: Optional[float] = None, **kwargs) -> Optional[float]:
        if operating_income is not None and revenue is not None and revenue != 0:
            return operating_income / revenue
        return None


class NetMarginCalculator(MetricCalculator):
    def calculate(self, net_income: Optional[float] = None, revenue: Optional[float] = None, **kwargs) -> Optional[float]:
        if net_income is not None and revenue is not None and revenue != 0:
            return net_income / revenue
        return None


class FcfYieldCalculator(MetricCalculator):
    def calculate(self, free_cash_flow: Optional[float] = None, market_cap: Optional[float] = None, **kwargs) -> Optional[float]:
        if free_cash_flow is not None and market_cap is not None and market_cap != 0:
            return free_cash_flow / market_cap
        return None


class FcfConversionCalculator(MetricCalculator):
    def calculate(self, free_cash_flow: Optional[float] = None, net_income: Optional[float] = None, **kwargs) -> Optional[float]:
        if free_cash_flow is not None and net_income is not None and net_income != 0:
            return free_cash_flow / net_income
        return None


class ShareholderYieldCalculator(MetricCalculator):
    def calculate(self, dividends: Optional[float] = None, buybacks: Optional[float] = None, market_cap: Optional[float] = None, **kwargs) -> Optional[float]:
        if market_cap is not None and market_cap != 0:
            total = -(dividends or 0) - (buybacks or 0)
            return total / market_cap
        return None


class GrossMarginStabilityCalculator(MetricCalculator):
    def calculate(self, gross_margins: Optional[list] = None, **kwargs) -> Optional[float]:
        if gross_margins is not None and len(gross_margins) > 1:
            return float(np.std(gross_margins))
        return None
