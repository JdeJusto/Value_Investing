from typing import Optional

from backend.analytics.calculator import MetricCalculator


class DcfCalculator(MetricCalculator):
    def calculate(
        self,
        free_cash_flow: Optional[float] = None,
        wacc: Optional[float] = None,
        growth_rate: float = 0.05,
        terminal_growth: float = 0.02,
        years: int = 5,
        **kwargs
    ) -> Optional[float]:
        if free_cash_flow is None:
            return None
        wacc = wacc if (wacc is not None and wacc > terminal_growth) else 0.08
        fcf_sum = 0.0
        for t in range(1, years + 1):
            fcf_t = free_cash_flow * (1 + growth_rate) ** t
            fcf_sum += fcf_t / ((1 + wacc) ** t)
        terminal_fcf = free_cash_flow * (1 + growth_rate) ** years * (1 + terminal_growth)
        terminal_value = terminal_fcf / (wacc - terminal_growth)
        terminal_pv = terminal_value / ((1 + wacc) ** years)
        return fcf_sum + terminal_pv
