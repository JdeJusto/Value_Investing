from backend.analytics.calculator import MetricCalculator


class RoicCalculator(MetricCalculator):
    def calculate(
        self,
        ebit: float | None = None,
        tax_rate: float = 0.21,
        total_debt: float | None = None,
        equity: float | None = None,
        cash: float | None = None,
        **kwargs,
    ) -> float | None:
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
        ebit_current: float | None = None,
        ebit_prior: float | None = None,
        tax_rate: float = 0.21,
        debt_current: float | None = None,
        debt_prior: float | None = None,
        equity_current: float | None = None,
        equity_prior: float | None = None,
        cash_current: float | None = None,
        cash_prior: float | None = None,
        **kwargs,
    ) -> float | None:
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
