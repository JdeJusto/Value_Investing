
from backend.analytics.calculator import MetricCalculator


class AltmanZScoreCalculator(MetricCalculator):
    def calculate(
        self,
        working_capital: float | None = None,
        total_assets: float | None = None,
        retained_earnings: float | None = None,
        ebit: float | None = None,
        market_cap: float | None = None,
        total_liabilities: float | None = None,
        revenue: float | None = None,
        **kwargs
    ) -> float | None:
        if any(v is None for v in [total_assets, total_liabilities, revenue]):
            return None
        if total_assets == 0:
            return None
        A = (working_capital or 0) / total_assets
        B = (retained_earnings or 0) / total_assets
        C = (ebit or 0) / total_assets
        D = (market_cap or 0) / total_liabilities if total_liabilities != 0 else 0
        E = revenue / total_assets
        z = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E
        return z
