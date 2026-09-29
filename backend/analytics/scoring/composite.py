
from backend.analytics.calculator import MetricCalculator


class CompositeScoreCalculator(MetricCalculator):
    def calculate(
        self,
        roe: float | None = None,
        pb: float | None = None,
        fcf_yield: float | None = None,
        operating_margin: float | None = None,
        **kwargs
    ) -> float:
        score = 0.0
        if roe is not None:
            score += roe * 0.25
        if pb is not None and pb != 0:
            score += (1.0 / pb) * 0.25
        if fcf_yield is not None:
            score += fcf_yield * 0.25
        if operating_margin is not None:
            score += operating_margin * 0.25
        return score
