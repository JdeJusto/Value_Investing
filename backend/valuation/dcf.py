"""A deterministic, data-only DCF valuation — labeled ``not-from-canon``.

This module answers "what is this company actually worth?" for high-multiple
compounders that the five book-derived methodologies (Graham, Buffett,
Graham & Dodd, Fisher) systematically reject because their source books
predate modern software/network economics.

It is NOT a methodology:

* it lives outside ``backend/methodologies/`` (no registry, no discovery),
* every output carries ``source="not-from-canon"``,
* ``compare-methodologies`` and ``methodologies list`` can never see it.

The module is a pure deterministic function of its inputs:

* ``fundamentals`` — a newest-first list of ``NormalizedFinancials`` (the
  canonical VO) supplied by the caller; the module never touches a DB,
* ``price_service`` — injected (real ``PriceService`` or a test stub); the
  module only ever calls ``get_current_price`` / ``get_market_cap`` /
  ``get_beta`` and never persists anything.

See ``backend/valuation/README.md`` for the full design.
"""

from __future__ import annotations

import statistics

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.common.company_type import is_financial
from backend.valuation.base import DCFAssumptions, DCFResult

#: Margin of safety is reported on a [-10, +10] band so a tiny denominator
#: cannot produce pathological percentages (e.g. -3000%).
_MOS_CAP = 10.0
#: FCF base = average of the newest N usable fiscal years.
_FCF_BASE_YEARS = 3
#: Revenue CAGR look-back window (in rows) for the 5-year growth estimate.
_CAGR_LOOKBACK_ROWS = 6
#: Two-stage projection horizon (years 1-5 fast, 6-10 half-speed).
_PROJECTION_YEARS = 10
#: Sensitivity grid step (±2% around WACC and growth).
_SENSITIVITY_STEP = 0.02

UNDERVALUED = "UNDERVALUED"
FAIR = "FAIR"
OVERVALUED = "OVERVALUED"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DCFValuation:
    """Two-stage discounted cash flow valuation with WACC + sensitivity."""

    def __init__(self, assumptions: DCFAssumptions | None = None) -> None:
        self.assumptions = assumptions or DCFAssumptions()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def evaluate(
        self,
        ticker: str,
        fundamentals: list[NormalizedFinancials],
        price_service,
    ) -> DCFResult:
        """Value one ticker. Deterministic; never persists anything.

        Args:
            ticker: Ticker symbol (upper-cased internally).
            fundamentals: Newest-first ``NormalizedFinancials`` rows.
            price_service: Object exposing ``get_current_price``,
                ``get_market_cap`` and ``get_beta`` (stubbed in tests).

        Returns:
            A :class:`DCFResult`; ``verdict`` is INSUFFICIENT_DATA whenever a
            required input is missing rather than a fabricated number.
        """
        ticker = (ticker or "").upper().strip()
        rows = [r for r in (fundamentals or []) if r is not None]
        result = DCFResult(
            ticker=ticker,
            intrinsic_value_per_share=None,
            current_price=None,
            margin_of_safety=None,
            verdict=INSUFFICIENT_DATA,
            wacc=None,
            fcf_base=None,
            fcf_years=None,
            growth_1_5=None,
            growth_6_10=None,
            terminal_growth=self.assumptions.terminal_growth,
            shares_outstanding=None,
        )
        if not rows:
            return self._insufficient(
                result,
                ["No fundamentals available for the ticker."],
                ["fundamentals"],
            )

        latest = rows[0]

        # A financial company (bank/insurer) has no free cash flow in the DCF
        # sense; bail out BEFORE projecting anything with a documented reason
        # (fixture dcf_financial_company.json carries this signature). The
        # shared company-type detector is used so the DCF never disagrees with
        # the methodologies about what a financial is.
        if is_financial(latest, getattr(latest, "sector", None)):
            return self._insufficient(
                result,
                [
                    (
                        "Financial company: DCF (free cash flow) does not apply "
                        "to banks/insurers."
                    )
                ],
                ["non-financial company"],
            )

        result.reasons = self._fcf_reasons(rows)
        fcf_values, fcf_years = self._fcf_base(rows)
        if not fcf_values:
            return self._insufficient(
                result,
                result.reasons
                + ["No free cash flow: operating cash flow/capex missing."],
                ["free cash flow"],
            )
        fcf_base = statistics.fmean(fcf_values)
        result.fcf_base = fcf_base
        result.fcf_years = fcf_years
        if fcf_base <= 0:
            return self._insufficient(
                result,
                result.reasons
                + [
                    f"Negative FCF (${fcf_base:,.0f}); DCF not applicable to cash-burning companies."
                ],
                ["positive free cash flow"],
            )

        # Shares outstanding (split-adjusted like the rest of the platform).
        shares = None
        if latest.shares_outstanding is not None:
            shares = latest.shares_outstanding * (latest.split_adjustment_factor or 1.0)
        result.shares_outstanding = shares
        if not shares or shares <= 0:
            return self._insufficient(
                result,
                result.reasons + ["Missing shares outstanding."],
                ["shares outstanding"],
            )

        # Growth: historical 5-year revenue CAGR, capped.
        result.reasons += self._growth_reasons(rows)
        growth_1_5, growth_6_10 = self._growth_rates(rows)
        result.growth_1_5 = growth_1_5
        result.growth_6_10 = growth_6_10

        # WACC from a simple model (or a CLI override).
        result.reasons += self._wacc_reasons(latest, price_service, ticker)
        wacc = self._wacc(latest, price_service, ticker, result)
        result.wacc = wacc
        if wacc <= self.assumptions.terminal_growth:
            return self._insufficient(
                result,
                result.reasons
                + [
                    (
                        f"WACC ({wacc:.2%}) <= terminal growth "
                        f"({self.assumptions.terminal_growth:.2%}); "
                        "terminal value is not defined."
                    ),
                ],
                ["wacc > terminal growth"],
            )

        value = self._project_value(
            fcf_base,
            shares,
            wacc,
            growth_1_5,
            growth_6_10,
            self.assumptions.terminal_growth,
        )
        if value is None or value <= 0:
            return self._insufficient(
                result,
                result.reasons + ["Intrinsic value not computable."],
                ["intrinsic value"],
            )

        price = price_service.get_current_price(ticker)
        result.current_price = price
        if price is None or price <= 0:
            return self._insufficient(
                result,
                result.reasons + ["Current price unavailable."],
                ["current price"],
            )

        result.sensitivity = self._sensitivity(
            fcf_base,
            shares,
            wacc,
            growth_1_5,
            self.assumptions.terminal_growth,
        )
        result.intrinsic_value_per_share = value
        raw_mos = (value - price) / value
        result.margin_of_safety = max(-_MOS_CAP, min(_MOS_CAP, raw_mos))
        result.verdict = self._verdict(result.margin_of_safety)
        return result

    # ------------------------------------------------------------------
    # inputs
    # ------------------------------------------------------------------
    @staticmethod
    def _fcf(row: NormalizedFinancials) -> float | None:
        """Free cash flow for one row: direct or OCF - capex."""
        if row.free_cash_flow is not None:
            return float(row.free_cash_flow)
        if row.operating_cash_flow is not None and row.capital_expenditure is not None:
            return float(row.operating_cash_flow) - float(row.capital_expenditure)
        return None

    def _fcf_base(self, rows):
        values = []
        years = []
        for row in rows[:_FCF_BASE_YEARS]:
            fcf = self._fcf(row)
            if fcf is not None:
                values.append(fcf)
                years.append(row.fiscal_year)
        return values, len(years)

    def _fcf_reasons(self, rows) -> list[str]:
        values, count = self._fcf_base(rows)
        if not values:
            return ["FCF base: no usable free-cash-flow year."]
        label = (
            "3-year average"
            if count >= 3
            else ("2-year average" if count == 2 else "latest year")
        )
        years = [
            row.fiscal_year
            for row in rows[:_FCF_BASE_YEARS]
            if self._fcf(row) is not None
        ]
        detail = f" (FY{', FY'.join(str(y) for y in years)})" if years else ""
        return [f"FCF base: {label} ${statistics.fmean(values):,.0f}{detail}."]

    def _growth_rates(self, rows):
        """(growth_1_5, growth_6_10) from 5-year revenue CAGR, capped."""
        override = self.assumptions.growth_override
        if override is not None:
            capped = min(float(override), self.assumptions.max_growth_years_1_5)
            return (
                capped,
                min(capped / 2.0, self.assumptions.max_growth_years_6_10),
            )

        rev_rows = [r for r in rows[:_CAGR_LOOKBACK_ROWS] if r.revenue]
        cagr = 0.0
        if len(rev_rows) >= 2:
            newest, oldest = rev_rows[0], rev_rows[-1]
            span = newest.fiscal_year - oldest.fiscal_year
            if span > 0 and newest.revenue > 0 and oldest.revenue > 0:
                cagr = (newest.revenue / oldest.revenue) ** (1.0 / span) - 1.0
        return (
            min(cagr, self.assumptions.max_growth_years_1_5),
            min(cagr / 2.0, self.assumptions.max_growth_years_6_10),
        )

    def _growth_reasons(self, rows) -> list[str]:
        override = self.assumptions.growth_override
        if override is not None:
            return [f"Growth years 1-5 overridden via CLI ({override:.2%})."]
        rev_rows = [r for r in rows[:_CAGR_LOOKBACK_ROWS] if r.revenue]
        if len(rev_rows) < 2:
            return ["No 5-year revenue history; assuming flat growth (0%)."]
        newest, oldest = rev_rows[0], rev_rows[-1]
        span = newest.fiscal_year - oldest.fiscal_year
        if span <= 0 or newest.revenue <= 0 or oldest.revenue <= 0:
            return ["No valid revenue span; assuming flat growth (0%)."]
        cagr = (newest.revenue / oldest.revenue) ** (1.0 / span) - 1.0
        return [f"Growth: {cagr:.1%} revenue CAGR over {span} fiscal years."]

    def _wacc_reasons(self, latest, price_service, ticker) -> list[str]:
        a = self.assumptions
        if a.wacc_override is not None:
            return [f"WACC overridden via CLI ({a.wacc_override:.2%})."]
        reasons = []
        beta = price_service.get_beta(ticker)
        if beta is None or beta <= 0:
            reasons.append("Beta unavailable or non-positive; assumed 1.0.")
        else:
            reasons.append(f"Beta {beta:.2f} from market data.")
        if (
            latest.interest_expense
            and latest.interest_expense > 0
            and latest.total_debt
            and latest.total_debt > 0
        ):
            reasons.append(
                f"Cost of debt {latest.interest_expense / latest.total_debt:.2%} (interest / total debt)."
            )
        else:
            reasons.append(
                "Cost of debt fallback = cost of equity (no interest/debt data)."
            )
        return reasons

    def _wacc(self, latest, price_service, ticker, result) -> float:
        """WACC = E/V * CoE + D/V * CoD * (1 - tax); overrides honored."""
        a = self.assumptions
        if a.wacc_override is not None:
            return float(a.wacc_override)

        beta = price_service.get_beta(ticker)
        if beta is None or beta <= 0:
            beta = 1.0
        cost_of_equity = a.risk_free_rate + beta * a.equity_risk_premium

        cost_of_debt = cost_of_equity
        if (
            latest.interest_expense
            and latest.interest_expense > 0
            and latest.total_debt
            and latest.total_debt > 0
        ):
            cost_of_debt = latest.interest_expense / latest.total_debt

        debt = (
            float(latest.total_debt)
            if latest.total_debt and latest.total_debt > 0
            else 0.0
        )
        equity = None
        market_cap = price_service.get_market_cap(ticker)
        if market_cap and market_cap > 0:
            equity = float(market_cap)
        elif latest.stockholders_equity and latest.stockholders_equity > 0:
            # Book equity fallback when no market value is available.
            equity = float(latest.stockholders_equity)

        if equity is None or equity <= 0:
            # All-equity fallback: no equity value can be priced.
            return cost_of_equity
        total = equity + debt
        e_weight = equity / total
        d_weight = debt / total
        return e_weight * cost_of_equity + d_weight * cost_of_debt * (1.0 - a.tax_rate)

    # ------------------------------------------------------------------
    # projection
    # ------------------------------------------------------------------
    @staticmethod
    def _project_value(
        fcf_base, shares, wacc, growth_1_5, growth_6_10, terminal_growth
    ):
        """Intrinsic value per share, or None when the inputs are degenerate."""
        if (
            not shares
            or shares <= 0
            or not fcf_base
            or fcf_base <= 0
            or wacc <= terminal_growth
            or (1.0 + growth_1_5) <= 0
            or (1.0 + growth_6_10) <= 0
        ):
            return None
        pv_sum = 0.0
        fcf = float(fcf_base)
        for year in range(1, _PROJECTION_YEARS + 1):
            g = growth_1_5 if year <= 5 else growth_6_10
            fcf *= 1.0 + g
            pv_sum += fcf / (1.0 + wacc) ** year
        terminal_value = fcf * (1.0 + terminal_growth) / (wacc - terminal_growth)
        pv_sum += terminal_value / (1.0 + wacc) ** _PROJECTION_YEARS
        return pv_sum / shares

    def _sensitivity(self, fcf_base, shares, wacc, growth_1_5, terminal_growth):
        """3x3 grid of intrinsic value per share for WACC x growth ±2%."""
        grid = {}
        for dw in (-_SENSITIVITY_STEP, 0.0, _SENSITIVITY_STEP):
            w = wacc + dw
            for dg in (-_SENSITIVITY_STEP, 0.0, _SENSITIVITY_STEP):
                g = growth_1_5 + dg
                g2 = min(g / 2.0, self.assumptions.max_growth_years_6_10)
                grid[(w, g)] = self._project_value(
                    fcf_base, shares, w, g, g2, terminal_growth
                )
        return grid

    # ------------------------------------------------------------------
    # verdict
    # ------------------------------------------------------------------
    @staticmethod
    def _verdict(mos: float) -> str:
        """Verdict from the capped margin of safety (see README thresholds)."""
        if mos >= 0.25:
            return UNDERVALUED
        if mos <= -0.10:
            return OVERVALUED
        return FAIR

    @staticmethod
    def _insufficient(result: DCFResult, reasons, missing) -> DCFResult:
        result.verdict = INSUFFICIENT_DATA
        result.reasons = reasons
        result.missing_inputs = missing
        result.sensitivity = {}
        return result
