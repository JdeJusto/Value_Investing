from typing import Optional

from backend.analytics.calculator import MetricCalculator


class RoicCalculator(MetricCalculator):
    def calculate(
        self,
        ebit: Optional[float] = None,
        tax_rate: float = 0.21,
        total_debt: Optional[float] = None,
        equity: Optional[float] = None,
        cash: Optional[float] = None,
        **kwargs
    ) -> Optional[float]:
        if ebit is None:
            return None
        nopat = ebit * (1 - tax_rate)
        debt = total_debt or 0
        eq = equity or 0
        c = cash or 0
        invested_capital = debt + eq - c
        if invested_capital == 0:
            return None
        return nopat / invested_capital


class IncrementalRoicCalculator(MetricCalculator):
    def calculate(
        self,
        ebit_current: Optional[float] = None,
        ebit_prior: Optional[float] = None,
        tax_rate: float = 0.21,
        debt_current: Optional[float] = None,
        debt_prior: Optional[float] = None,
        equity_current: Optional[float] = None,
        equity_prior: Optional[float] = None,
        cash_current: Optional[float] = None,
        cash_prior: Optional[float] = None,
        **kwargs
    ) -> Optional[float]:
        if any(v is None for v in [ebit_current, ebit_prior]):
            return None
        nopat0 = ebit_current * (1 - tax_rate)
        nopat1 = ebit_prior * (1 - tax_rate)
        ic0 = (debt_current or 0) + (equity_current or 0) - (cash_current or 0)
        ic1 = (debt_prior or 0) + (equity_prior or 0) - (cash_prior or 0)
        delta_nopat = nopat0 - nopat1
        delta_ic = ic0 - ic1
        if delta_ic == 0:
            return None
        return delta_nopat / delta_ic
