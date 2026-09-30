from backend.analytics.calculator import MetricCalculator


class PbCalculator(MetricCalculator):
    def calculate(
        self, market_cap: float | None = None, equity: float | None = None, **kwargs
    ) -> float | None:
        if market_cap is not None and equity is not None and equity != 0:
            return market_cap / equity
        return None


class EvEbitCalculator(MetricCalculator):
    def calculate(
        self, enterprise_value: float | None = None, ebit: float | None = None, **kwargs
    ) -> float | None:
        if enterprise_value is not None and ebit is not None and ebit != 0:
            return enterprise_value / ebit
        return None


class NetDebtToEbitdaCalculator(MetricCalculator):
    def calculate(
        self,
        total_debt: float | None = None,
        cash: float | None = None,
        ebitda: float | None = None,
        **kwargs,
    ) -> float | None:
        if total_debt is None or ebitda is None or ebitda == 0:
            return None
        # A missing share count is not a zero net debt: without debt data the
        # ratio cannot be computed, so it degrades to N/A instead of returning
        # a misleading negative number ((-cash) / ebitda).
        net_debt = total_debt - (cash or 0)
        return net_debt / ebitda


class InterestCoverageCalculator(MetricCalculator):
    def calculate(
        self, ebit: float | None = None, interest_expense: float | None = None, **kwargs
    ) -> float | None:
        if ebit is None or interest_expense is None or interest_expense == 0:
            return None
        return ebit / abs(interest_expense)


class CroicCalculator(MetricCalculator):
    def calculate(
        self,
        free_cash_flow: float | None = None,
        invested_capital: float | None = None,
        **kwargs,
    ) -> float | None:
        if (
            free_cash_flow is not None
            and invested_capital is not None
            and invested_capital != 0
        ):
            return free_cash_flow / invested_capital
        return None


class OwnerEarningsCalculator(MetricCalculator):
    def calculate(
        self,
        net_income: float | None = None,
        depreciation: float | None = None,
        maintenance_capex: float | None = None,
        working_capital_change: float | None = None,
        **kwargs,
    ) -> float | None:
        if any(v is None for v in [net_income, depreciation, maintenance_capex]):
            return None
        owner = net_income + depreciation - maintenance_capex
        if working_capital_change is not None:
            owner -= working_capital_change
        return owner
