
from backend.analytics.calculator import MetricCalculator


class OperatingMarginCalculator(MetricCalculator):
    def calculate(
        self,
        operating_income: float | None = None,
        revenue: float | None = None,
        **kwargs
    ) -> float | None:
        if operating_income is not None and revenue is not None and revenue != 0:
            return operating_income / revenue
        return None


class NetMarginCalculator(MetricCalculator):
    def calculate(
        self,
        net_income: float | None = None,
        revenue: float | None = None,
        **kwargs
    ) -> float | None:
        if net_income is not None and revenue is not None and revenue != 0:
            return net_income / revenue
        return None


class FcfYieldCalculator(MetricCalculator):
    def calculate(
        self,
        free_cash_flow: float | None = None,
        market_cap: float | None = None,
        **kwargs
    ) -> float | None:
        if free_cash_flow is not None and market_cap is not None and market_cap != 0:
            return free_cash_flow / market_cap
        return None


class FcfConversionCalculator(MetricCalculator):
    def calculate(
        self,
        free_cash_flow: float | None = None,
        net_income: float | None = None,
        **kwargs
    ) -> float | None:
        if free_cash_flow is not None and net_income is not None and net_income != 0:
            return free_cash_flow / net_income
        return None


class ShareholderYieldCalculator(MetricCalculator):
    def calculate(
        self,
        dividends: float | None = None,
        buybacks: float | None = None,
        market_cap: float | None = None,
        **kwargs
    ) -> float | None:
        if market_cap is not None and market_cap != 0:
            total = abs(dividends or 0) + abs(buybacks or 0)
            return total / market_cap
        return None


class GrossMarginStabilityCalculator(MetricCalculator):
    def calculate(
        self, gross_margins: list | None = None, **kwargs
    ) -> float | None:
        if gross_margins is not None and len(gross_margins) > 1:
            import numpy as np

            return float(np.std(gross_margins))
        return None
