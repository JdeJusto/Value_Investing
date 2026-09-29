
from backend.analytics.calculator import MetricCalculator


class PiotroskiFScoreCalculator(MetricCalculator):
    def calculate(
        self,
        roa_current: float | None = None,
        roa_prior: float | None = None,
        cfo_current: float | None = None,
        net_income_current: float | None = None,
        total_assets_current: float | None = None,
        total_assets_prior: float | None = None,
        total_debt_current: float | None = None,
        total_debt_prior: float | None = None,
        working_capital_current: float | None = None,
        working_capital_prior: float | None = None,
        revenue_current: float | None = None,
        revenue_prior: float | None = None,
        cogs_current: float | None = None,
        cogs_prior: float | None = None,
        **kwargs
    ) -> int | None:
        try:
            score = 0

            # 1. ROA is positive
            if roa_current is not None and roa_current > 0:
                score += 1

            # 2. CFO is positive
            if cfo_current is not None and cfo_current > 0:
                score += 1

            # 3. ROA improvement
            if (
                roa_current is not None
                and roa_prior is not None
                and roa_current > roa_prior
            ):
                score += 1

            # 4. Accruals: CFO > Net Income (high quality earnings)
            if (
                cfo_current is not None
                and net_income_current is not None
                and cfo_current > net_income_current
            ):
                score += 1

            # 5. Leverage decrease
            lev_ratio_current = (
                (total_debt_current or 0) / total_assets_current
                if total_assets_current
                else None
            )
            lev_ratio_prior = (
                (total_debt_prior or 0) / total_assets_prior
                if total_assets_prior
                else None
            )
            if (
                lev_ratio_current is not None
                and lev_ratio_prior is not None
                and lev_ratio_current < lev_ratio_prior
            ):
                score += 1

            # 6. Liquidity increase (working capital to total assets proxy
            #    of the current ratio; no current assets/liabilities fields)
            liq_current = (
                (working_capital_current or 0) / total_assets_current
                if total_assets_current
                else None
            )
            liq_prior = (
                (working_capital_prior or 0) / total_assets_prior
                if total_assets_prior
                else None
            )
            if (
                liq_current is not None
                and liq_prior is not None
                and liq_current > liq_prior
            ):
                score += 1

            # 7. No share dilution (not implemented — needs shares outstanding data)

            # 8. Gross margin improvement
            gm_current = (
                ((revenue_current or 0) - (cogs_current or 0)) / revenue_current
                if revenue_current
                else None
            )
            gm_prior = (
                ((revenue_prior or 0) - (cogs_prior or 0)) / revenue_prior
                if revenue_prior
                else None
            )
            if (
                gm_current is not None
                and gm_prior is not None
                and gm_current > gm_prior
            ):
                score += 1

            # 9. Asset turnover improvement
            at_current = (
                revenue_current / total_assets_current
                if (revenue_current and total_assets_current)
                else None
            )
            at_prior = (
                revenue_prior / total_assets_prior
                if (revenue_prior and total_assets_prior)
                else None
            )
            if (
                at_current is not None
                and at_prior is not None
                and at_current > at_prior
            ):
                score += 1

            return score
        except Exception:
            return None
