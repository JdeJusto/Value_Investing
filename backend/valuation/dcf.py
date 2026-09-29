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
from itertools import pairwise

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.common.company_type import (
    CompanyType,
    detect_company_type,
)
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

        The company-type detector decides which cash flow a company is
        honestly valued on, and ``result.variant`` records which one ran:
        ``standard`` (free cash flow, the historical pipeline), ``reit``
        (funds from operations), ``ddm_financial`` (a Gordon dividend
        discount model for banks/insurers) and ``hyper_growth`` (the observed
        positive FCF years of a cash-burning name). Nothing is fabricated: a
        variant that cannot be computed from the data returns
        INSUFFICIENT_DATA with the missing input named.
        """
        ticker = (ticker or "").upper().strip()
        rows = [r for r in (fundamentals or []) if r is not None]
        if not rows:
            return self._insufficient(
                self._base_result(ticker),
                ["No fundamentals available for the ticker."],
                ["fundamentals"],
            )

        latest = rows[0]
        company_type = detect_company_type(
            latest, rows, getattr(latest, "sector", None)
        )
        if company_type is CompanyType.FINANCIAL:
            return self._evaluate_financial(ticker, rows, price_service)
        if company_type is CompanyType.REIT:
            return self._evaluate_reit(ticker, rows, price_service)
        if company_type is CompanyType.HYPER_GROWTH:
            return self._evaluate_hyper_growth(ticker, rows, price_service)
        # STANDARD and UTILITY both keep the historical free-cash-flow DCF.
        return self._evaluate_standard(ticker, rows, price_service)

    def _base_result(self, ticker: str) -> DCFResult:
        """A fresh, empty DCFResult with the module defaults and source."""
        return DCFResult(
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

    def _evaluate_standard(self, ticker: str, rows, price_service) -> DCFResult:
        """The historical two-stage free-cash-flow DCF (variant ``standard``).

        Used for every company whose cash flow is honestly free cash flow
        (STANDARD shapes and utilities); the body below is the module's
        long-standing pipeline, unchanged.
        """
        result = self._base_result(ticker)
        latest = rows[0]

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
    # company-type variants (dispatched from evaluate)
    # ------------------------------------------------------------------
    @staticmethod
    def _ffo(row: NormalizedFinancials) -> float | None:
        """Funds from operations (approximation): net income + depreciation.

        Property-sale gains — the other standard FFO adjustment — are not
        present in the normalized value object, so they are omitted rather
        than guessed. Positive in healthy REITs where free cash flow is
        negative.
        """
        if row.net_income is None or row.depreciation_amortization is None:
            return None
        return float(row.net_income) + float(row.depreciation_amortization)

    def _ffo_base(self, rows):
        """(FFO values, count) over the newest usable fiscal years."""
        values, years = [], []
        for row in rows[:_FCF_BASE_YEARS]:
            ffo = self._ffo(row)
            if ffo is not None:
                values.append(ffo)
                years.append(row.fiscal_year)
        return values, len(years)

    def _evaluate_reit(self, ticker: str, rows, price_service) -> DCFResult:
        """REIT DCF on funds from operations (variant ``reit``).

        Heavy depreciation makes free cash flow negative for perfectly healthy
        landlords, so a straight FCF DCF would call them cash burners; FFO
        (net income + D&A, an approximation) is what the market capitalizes.
        """
        result = self._base_result(ticker)
        result.variant = "reit"
        latest = rows[0]
        result.reasons = [
            (
                "REIT (real estate): valued on funds from operations instead "
                "of free cash flow — heavy depreciation makes FCF negative "
                "for healthy landlords. FFO approximated as net income + "
                "depreciation & amortization (property-sale gains are not "
                "available in the normalized data)."
            )
        ]

        ffo_values, ffo_years = self._ffo_base(rows)
        if not ffo_values:
            return self._insufficient(
                result,
                result.reasons + ["No FFO: net income/depreciation missing."],
                ["funds from operations"],
            )
        ffo_base = statistics.fmean(ffo_values)
        result.fcf_base = ffo_base
        result.fcf_years = ffo_years
        if ffo_base <= 0:
            return self._insufficient(
                result,
                result.reasons
                + [f"Negative FFO (${ffo_base:,.0f}); REIT DCF not applicable."],
                ["positive funds from operations"],
            )

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

        result.reasons += self._growth_reasons(rows)
        growth_1_5, growth_6_10 = self._growth_rates(rows)
        result.growth_1_5 = growth_1_5
        result.growth_6_10 = growth_6_10

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
                    )
                ],
                ["wacc > terminal growth"],
            )

        value = self._project_value(
            ffo_base,
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
            ffo_base,
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

    def _evaluate_financial(self, ticker: str, rows, price_service) -> DCFResult:
        """Financial companies (banks/insurers): a Gordon dividend discount
        model (variant ``ddm_financial``).

        A financial company has no free cash flow in the DCF sense — its cash
        flow is dominated by operating asset/liability flows — so the only
        honest cash a shareholder can expect is the dividend stream. No
        dividends in the data reads INSUFFICIENT_DATA; the value is never
        fabricated.
        """
        result = self._base_result(ticker)
        result.variant = "ddm_financial"
        latest = rows[0]

        shares = None
        if latest.shares_outstanding is not None:
            shares = latest.shares_outstanding * (latest.split_adjustment_factor or 1.0)
        result.shares_outstanding = shares
        if shares is None or shares <= 0:
            return self._insufficient(
                result,
                [
                    (
                        "Financial company (banks/insurers): free cash flow "
                        "does not apply, so a dividend discount model is used "
                        "instead."
                    ),
                    "Missing shares outstanding.",
                ],
                ["shares outstanding"],
            )

        # Split-restated dividend per share over the usable window.
        dps_stream = []
        for row in rows[:_FCF_BASE_YEARS]:
            if row.dividends_paid is not None and row.shares_outstanding:
                s = row.shares_outstanding * (row.split_adjustment_factor or 1.0)
                if s > 0:
                    dps_stream.append(float(row.dividends_paid) / s)
        if not dps_stream or dps_stream[0] <= 0:
            return self._insufficient(
                result,
                [
                    (
                        "Financial company (banks/insurers): free cash flow "
                        "does not apply, so a dividend discount model is used "
                        "instead."
                    ),
                    "No dividends paid in the latest year; the DDM requires a dividend stream.",
                ],
                ["dividends per share"],
            )
        dps = dps_stream[0]
        result.fcf_base = dps  # rendered as "Dividend per share" by the CLI
        result.fcf_years = len(dps_stream)

        # Dividend growth: average year-over-year DPS growth across the stream,
        # newest-first (newer / older - 1); 0% when there is not enough history
        # to measure it. Allowed to be negative when a bank actually cut its
        # dividend.
        g = 0.0
        if len(dps_stream) >= 2:
            deltas = [
                a / b - 1.0
                for a, b in pairwise(dps_stream)
                if a and a > 0 and b and b > 0
            ]
            if deltas:
                g = statistics.fmean(deltas)
        g = min(g, self.assumptions.max_growth_years_1_5)
        result.growth_1_5 = g
        result.growth_6_10 = min(g / 2.0, self.assumptions.max_growth_years_6_10)

        beta = price_service.get_beta(ticker)
        if beta is None or beta <= 0:
            beta = 1.0
        coe = (
            self.assumptions.risk_free_rate
            + beta * self.assumptions.equity_risk_premium
        )
        result.wacc = coe  # discount rate: the cost of equity, not WACC

        if coe <= g:
            return self._insufficient(
                result,
                [
                    ("Financial company (banks/insurers): dividend discount model."),
                    (
                        f"Cost of equity ({coe:.2%}) <= dividend growth "
                        f"({g:.2%}); Gordon growth is not defined."
                    ),
                ],
                ["cost of equity > dividend growth"],
            )

        value = dps * (1.0 + g) / (coe - g)
        if value is None or value <= 0:
            return self._insufficient(
                result,
                [
                    "Financial company (banks/insurers): dividend discount model.",
                    "Intrinsic value not computable.",
                ],
                ["intrinsic value"],
            )

        price = price_service.get_current_price(ticker)
        result.current_price = price
        if price is None or price <= 0:
            return self._insufficient(
                result,
                [
                    "Financial company (banks/insurers): dividend discount model.",
                    "Current price unavailable.",
                ],
                ["current price"],
            )

        result.intrinsic_value_per_share = value
        raw_mos = (value - price) / value
        result.margin_of_safety = max(-_MOS_CAP, min(_MOS_CAP, raw_mos))
        result.verdict = self._verdict(result.margin_of_safety)
        result.reasons = [
            (
                "Financial company (banks/insurers): free cash flow does not "
                "apply; valued with a Gordon dividend discount model."
            ),
            (
                f"Dividend {dps:.2f}/share (split-restated) from "
                f"{len(dps_stream)} year(s) of dividend data."
            ),
            (
                f"Dividend growth {g:.1%}; cost of equity {coe:.2%} "
                f"(risk-free {self.assumptions.risk_free_rate:.0%} + beta "
                f"{beta:.2f} x ERP {self.assumptions.equity_risk_premium:.0%})."
            ),
            "Single-stage Gordon growth: no WACC/growth sensitivity grid.",
        ]
        return result

    def _evaluate_hyper_growth(self, ticker: str, rows, price_service) -> DCFResult:
        """Hyper-growth DCF on observed positive FCF (variant
        ``hyper_growth``).

        These names burn cash while growing fast, so the standard pipeline
        bails on their negative FCF base. Instead the base is the mean of the
        *observed* positive FCF years in the window — averaging actual
        figures, never fabricating one — with the (capped) revenue CAGR as
        growth. A company still FCF-negative in every recent year reads
        INSUFFICIENT_DATA.
        """
        result = self._base_result(ticker)
        result.variant = "hyper_growth"
        latest = rows[0]
        result.reasons = [
            (
                "Hyper-growth (revenue CAGR > 25%, currently FCF-negative): "
                "value anchored on the observed positive free-cash-flow years "
                "in the window — no cash flow is ever fabricated. Names still "
                "FCF-negative in every recent year read INSUFFICIENT_DATA."
            )
        ]

        candidates = [self._fcf(row) for row in rows[:_FCF_BASE_YEARS]]
        positives = [v for v in candidates if v is not None and v > 0]
        if not positives:
            return self._insufficient(
                result,
                result.reasons
                + [
                    (
                        f"No positive free cash flow in the last "
                        f"{_FCF_BASE_YEARS} years; DCF is not applicable at "
                        "this cash-burning stage."
                    )
                ],
                ["positive free cash flow"],
            )
        fcf_base = statistics.fmean(positives)
        result.fcf_base = fcf_base
        result.fcf_years = len(positives)

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

        result.reasons += self._growth_reasons(rows)
        growth_1_5, growth_6_10 = self._growth_rates(rows)
        result.growth_1_5 = growth_1_5
        result.growth_6_10 = growth_6_10

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
                    )
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
