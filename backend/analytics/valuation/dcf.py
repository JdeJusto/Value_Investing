from typing import Optional

from backend.analytics.calculator import MetricCalculator


class DcfCalculator(MetricCalculator):
    def calculate(
        self,
        free_cash_flow: float | None = None,
        wacc: float | None = None,
        growth_rate: float = 0.05,
        terminal_growth: float = 0.02,
        years: int = 5,
        **kwargs
    ) -> float | None:
        if free_cash_flow is None:
            return None
        if wacc is None or not (0.0 < terminal_growth < wacc < 0.5):
            wacc = 0.08
        if not (-0.5 <= growth_rate < wacc):
            growth_rate = 0.05
        fcf_sum = 0.0
        for t in range(1, years + 1):
            fcf_t = free_cash_flow * (1 + growth_rate) ** t
            fcf_sum += fcf_t / ((1 + wacc) ** t)
        terminal_fcf = (
            free_cash_flow * (1 + growth_rate) ** years * (1 + terminal_growth)
        )
        terminal_value = terminal_fcf / (wacc - terminal_growth)
        terminal_pv = terminal_value / ((1 + wacc) ** years)
        return fcf_sum + terminal_pv
