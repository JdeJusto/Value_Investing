from typing import Optional

from backend.analytics.calculator import MetricCalculator


class PbCalculator(MetricCalculator):
    def calculate(self, market_cap: Optional[float] = None, equity: Optional[float] = None, **kwargs) -> Optional[float]:
        if market_cap is not None and equity is not None and equity != 0:
            return market_cap / equity
        return None


class EvEbitCalculator(MetricCalculator):
    def calculate(self, enterprise_value: Optional[float] = None, ebit: Optional[float] = None, **kwargs) -> Optional[float]:
        if enterprise_value is not None and ebit is not None and ebit != 0:
            return enterprise_value / ebit
        return None


class NetDebtToEbitdaCalculator(MetricCalculator):
    def calculate(self, total_debt: Optional[float] = None, cash: Optional[float] = None, ebitda: Optional[float] = None, **kwargs) -> Optional[float]:
        if ebitda is None or ebitda == 0:
            return None
        net_debt = (total_debt or 0) - (cash or 0)
        return net_debt / ebitda


class InterestCoverageCalculator(MetricCalculator):
    def calculate(self, ebit: Optional[float] = None, interest_expense: Optional[float] = None, **kwargs) -> Optional[float]:
        if ebit is None or interest_expense is None or interest_expense == 0:
            return None
        return ebit / interest_expense


class CroicCalculator(MetricCalculator):
    def calculate(self, free_cash_flow: Optional[float] = None, invested_capital: Optional[float] = None, **kwargs) -> Optional[float]:
        if free_cash_flow is not None and invested_capital is not None and invested_capital != 0:
            return free_cash_flow / invested_capital
        return None


class OwnerEarningsCalculator(MetricCalculator):
    def calculate(self, net_income: Optional[float] = None, depreciation: Optional[float] = None, maintenance_capex: Optional[float] = None, working_capital_change: Optional[float] = None, **kwargs) -> Optional[float]:
        if any(v is None for v in [net_income, depreciation, maintenance_capex]):
            return None
        owner = net_income + depreciation - maintenance_capex
        if working_capital_change is not None:
            owner -= working_capital_change
        return owner
