"""Company analysis built exclusively on normalized financial data.

This service reads canonical :class:`NormalizedFinancials` from a
:class:`FinancialRepository` and market data from a
:class:`MarketDataProvider`. It never calls financial providers directly;
when data is missing it may request ingestion through an injected
:class:`DataLoader` (the data pipeline), but all computation happens on
normalized, persisted records.
"""

from __future__ import annotations

import logging
from typing import Optional

import backend.core.config as _config
from backend.analytics.ratios.debt_to_equity import DebtToEquityCalculator
from backend.analytics.ratios.leverage import (
    CroicCalculator,
    EvEbitCalculator,
    InterestCoverageCalculator,
    NetDebtToEbitdaCalculator,
    OwnerEarningsCalculator,
    PbCalculator,
)
from backend.analytics.ratios.margins import (
    FcfConversionCalculator,
    FcfYieldCalculator,
    GrossMarginStabilityCalculator,
    NetMarginCalculator,
    OperatingMarginCalculator,
    ShareholderYieldCalculator,
)
from backend.analytics.ratios.per import PerCalculator
from backend.analytics.ratios.roe import RoeCalculator
from backend.analytics.ratios.roic import IncrementalRoicCalculator, RoicCalculator
from backend.analytics.scoring.altman_z import AltmanZScoreCalculator
from backend.analytics.scoring.composite import CompositeScoreCalculator
from backend.analytics.scoring.piotroski import PiotroskiFScoreCalculator
from backend.analytics.valuation.dcf import DcfCalculator
from backend.domain.interfaces.data_loader import DataLoader
from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.interfaces.provider import MarketDataProvider
from backend.domain.services import needs_refresh
from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.intelligence.scoring_model import assess_investment, confidence_level

logger = logging.getLogger("backend.analytics")

DEFAULT_TAX_RATE = _config.DEFAULT_TAX_RATE
DEFAULT_WACC = _config.DEFAULT_WACC
DEFAULT_MARKET_RETURN = _config.DEFAULT_MARKET_RETURN
DEFAULT_RISK_FREE_RATE = 0.04
DEFAULT_COST_OF_DEBT = 0.05

HIGH_CONFIDENCE_QUALITY = 0.7
HIGH_CONFIDENCE_COVERAGE = 0.8
MEDIUM_CONFIDENCE_COVERAGE = 0.5

# Years of usable history that count as full quality data; thinner
# histories get proportionally lower derived quality scores.
REQUIRED_HISTORY_YEARS = 8


def _equity_of(financials: NormalizedFinancials) -> Optional[float]:
    if financials.stockholders_equity is not None:
        return financials.stockholders_equity
    if financials.total_assets is not None and financials.total_liabilities is not None:
        return financials.total_assets - financials.total_liabilities
    return None


def _effective_tax_rate(financials: Optional[NormalizedFinancials]) -> Optional[float]:
    if not financials or financials.tax_provision is None:
        return None
    if not financials.pretax_income or financials.pretax_income == 0:
        return None
    return financials.tax_provision / financials.pretax_income


def _sanitize_tax_rate(rate: Optional[float], default: float) -> float:
    if rate is None:
        return default
    return min(max(rate, 0.0), 1.0)


class CompanyAnalysisService:
    """Computes valuation metrics from persisted normalized financials."""

    def __init__(
        self,
        repository: FinancialRepository,
        market_provider: MarketDataProvider,
        loader: Optional[DataLoader] = None,
        default_tax_rate: float = DEFAULT_TAX_RATE,
        default_wacc: float = DEFAULT_WACC,
        market_return: float = DEFAULT_MARKET_RETURN,
        risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    ):
        self._repository = repository
        self._market = market_provider
        self._loader = loader
        self._default_tax_rate = default_tax_rate
        self._default_wacc = default_wacc
        self._market_return = market_return
        self._risk_free_rate = risk_free_rate

    # ------------------------------------------------------------------
    def analyze(self, ticker: str) -> Optional[dict]:
        """Compute the full metric suite for a ticker, or None if no data."""
        rows = self._load_history(ticker)
        if not rows:
            return None

        year_lookup = {row.fiscal_year: row for row in rows}
        fiscal_years = sorted(year_lookup, reverse=True)
        current_year = fiscal_years[0]
        prior_year = fiscal_years[1] if len(fiscal_years) > 1 else None

        last = year_lookup[current_year]
        prior = year_lookup.get(prior_year) if prior_year else None

        market_cap = self._safe_market(self._market.get_market_cap, ticker)
        ev = self._safe_market(self._market.get_enterprise_value, ticker)

        equity = _equity_of(last)
        ebit = last.ebit
        net_income = last.net_income
        revenue = last.revenue
        op_income = last.operating_income
        cash = last.cash_and_equivalents
        debt = last.total_debt
        assets = last.total_assets
        liab = last.total_liabilities
        wc = last.working_capital
        re = last.retained_earnings
        fcf = last.free_cash_flow
        cfo = last.operating_cash_flow
        da = last.depreciation_amortization
        dividends = last.dividends_paid
        buybacks = last.repurchase_of_stock
        maintenance_capex = last.capital_expenditure

        ebitda = last.ebitda
        if ebitda is None and ebit is not None and da is not None:
            ebitda = ebit + da

        gross_margins = self._gross_margins(rows)
        tax_rate = _sanitize_tax_rate(_effective_tax_rate(last), self._default_tax_rate)
        wacc = self._wacc(ticker, last) or self._default_wacc

        roa_current = None
        roa_prior = None
        if net_income is not None and assets and assets != 0:
            roa_current = net_income / assets
        if prior and prior.net_income is not None and prior.total_assets:
            roa_prior = prior.net_income / prior.total_assets

        invested_capital = None
        if debt is not None and equity is not None:
            invested_capital = debt + equity - (cash or 0)

        result = {
            "ticker": ticker,
            "market_cap": market_cap,
            "revenue": revenue,
            "net_income": net_income,
            "ebit": ebit,
            "fcf": fcf,
            "total_debt": debt,
            "equity": equity,
            "cash_and_equivalents": cash,
        }

        result["roe"] = RoeCalculator().calculate(net_income=net_income, equity=equity)
        result["per"] = PerCalculator().calculate(
            market_cap=market_cap, net_income=net_income
        )
        result["debt_to_equity"] = DebtToEquityCalculator().calculate(
            total_debt=debt, equity=equity
        )
        if revenue is not None and prior is not None and prior.revenue:
            result["revenue_growth"] = (revenue - prior.revenue) / prior.revenue
        result["pb"] = PbCalculator().calculate(market_cap=market_cap, equity=equity)
        result["roic"] = RoicCalculator().calculate(
            ebit=ebit,
            tax_rate=tax_rate,
            total_debt=debt,
            equity=equity,
            cash=cash,
        )
        result["incremental_roic"] = IncrementalRoicCalculator().calculate(
            ebit_current=ebit,
            ebit_prior=prior.ebit if prior else None,
            tax_rate=tax_rate,
            debt_current=debt,
            debt_prior=prior.total_debt if prior else None,
            equity_current=equity,
            equity_prior=_equity_of(prior) if prior else None,
            cash_current=cash,
            cash_prior=prior.cash_and_equivalents if prior else None,
        )
        result["operating_margin"] = OperatingMarginCalculator().calculate(
            operating_income=op_income,
            revenue=revenue,
        )
        result["net_margin"] = NetMarginCalculator().calculate(
            net_income=net_income,
            revenue=revenue,
        )
        result["fcf_yield"] = FcfYieldCalculator().calculate(
            free_cash_flow=fcf,
            market_cap=market_cap,
        )
        result["ev_ebit"] = EvEbitCalculator().calculate(
            enterprise_value=ev,
            ebit=ebit,
        )
        result["acquirers_multiple"] = result["ev_ebit"]
        result["owner_earnings"] = OwnerEarningsCalculator().calculate(
            net_income=net_income,
            depreciation=da,
            maintenance_capex=maintenance_capex,
            working_capital_change=last.working_capital_change,
        )
        result["piotroski_fscore"] = PiotroskiFScoreCalculator().calculate(
            roa_current=roa_current,
            roa_prior=roa_prior,
            cfo_current=cfo,
            net_income_current=net_income,
            total_assets_current=assets,
            total_assets_prior=prior.total_assets if prior else None,
            total_debt_current=debt,
            total_debt_prior=prior.total_debt if prior else None,
            working_capital_current=wc,
            working_capital_prior=prior.working_capital if prior else None,
            revenue_current=revenue,
            revenue_prior=prior.revenue if prior else None,
            cogs_current=last.cogs,
            cogs_prior=prior.cogs if prior else None,
        )
        result["altman_zscore"] = AltmanZScoreCalculator().calculate(
            working_capital=wc,
            total_assets=assets,
            retained_earnings=re,
            ebit=ebit,
            market_cap=market_cap,
            total_liabilities=liab,
            revenue=revenue,
        )
        result["net_debt_to_ebitda"] = NetDebtToEbitdaCalculator().calculate(
            total_debt=debt,
            cash=cash,
            ebitda=ebitda,
        )
        result["interest_coverage"] = InterestCoverageCalculator().calculate(
            ebit=ebit,
            interest_expense=last.interest_expense,
        )
        result["gross_margin_stability"] = GrossMarginStabilityCalculator().calculate(
            gross_margins=gross_margins,
        )
        result["fcf_conversion"] = FcfConversionCalculator().calculate(
            free_cash_flow=fcf,
            net_income=net_income,
        )
        result["croic"] = CroicCalculator().calculate(
            free_cash_flow=fcf,
            invested_capital=invested_capital,
        )
        result["dcf_value"] = DcfCalculator().calculate(
            free_cash_flow=fcf,
            wacc=wacc,
        )
        result["shareholder_yield"] = ShareholderYieldCalculator().calculate(
            dividends=dividends,
            buybacks=buybacks,
            market_cap=market_cap,
        )
        result["score"] = CompositeScoreCalculator().calculate(
            roe=result["roe"],
            pb=result["pb"],
            fcf_yield=result["fcf_yield"],
            operating_margin=result["operating_margin"],
        )

        result.update(self._data_reliability(ticker, rows))
        result.update(self._market_edge(ticker, result.get("dcf_value")))
        result.update(assess_investment(rows, result))

        return result

    # ------------------------------------------------------------------
    # Fields that any real (completed) fiscal year must populate; an
    # all-empty row is an in-progress year with no filings yet and must
    # not be treated as the current year.
    _CORE_FIELDS = (
        "revenue",
        "net_income",
        "ebit",
        "ebitda",
        "operating_income",
        "operating_cash_flow",
        "free_cash_flow",
        "total_assets",
    )

    @classmethod
    def _row_has_data(cls, row: NormalizedFinancials) -> bool:
        return any(getattr(row, field) is not None for field in cls._CORE_FIELDS)

    def _load_history(self, ticker: str) -> list[NormalizedFinancials]:
        rows = self._repository.get_best_available(ticker)
        if rows and needs_refresh(rows):
            rows = self._refresh_history(ticker)
        if not rows and self._loader is not None:
            try:
                self._loader.load_ticker(ticker)
                rows = self._repository.get_best_available(ticker)
            except Exception:  # noqa: BLE001 — missing data must not kill analysis
                logger.warning("analytics: could not load data for %s", ticker)
        # Drop all-empty (in-progress) years so the "current year" is always a
        # completed fiscal year with actual values.
        return [row for row in rows if self._row_has_data(row)]

    def _refresh_history(self, ticker: str) -> list[NormalizedFinancials]:
        if self._loader is None:
            return self._repository.get_best_available(ticker)
        try:
            self._loader.load_ticker(ticker, force=True)
        except Exception:  # noqa: BLE001
            logger.warning("analytics: could not refresh data for %s", ticker)
        return self._repository.get_best_available(ticker)

    def _data_reliability(self, ticker: str, rows: list[NormalizedFinancials]) -> dict:
        """Source consistency, confidence and quality metadata for the result.

        When ``data_quality_score`` / ``data_completeness`` are not set in the
        persisted rows (as is the case when fundamentals are reconstructed from
        the Financial-DataBase), a derived quality metric is computed from the
        depth of available history and the coverage ratio so the composite
        score and confidence carry real signal.
        """
        all_rows = self._repository.list_all(ticker)
        available_years = {r.fiscal_year for r in all_rows}
        used_years = {r.fiscal_year for r in rows}
        coverage = len(used_years) / len(available_years) if available_years else 0.0
        # Depth: fraction of REQUIRED_HISTORY_YEARS we have; capped at 1.0.
        depth = min(len(used_years), REQUIRED_HISTORY_YEARS) / REQUIRED_HISTORY_YEARS

        sources = sorted({r.source for r in rows})

        if len(sources) > 1:
            data_source_used = "MIXED"
        else:
            data_source_used = sources[0].value.upper() if sources else "UNKNOWN"

        quality_raw = self._mean(r.data_quality_score for r in rows)
        completeness_raw = self._mean(r.data_completeness for r in rows)

        # Derived fallbacks: quality from history depth, completeness from
        # data coverage — both concrete, deterministic numbers that scale
        # with how much usable history is available.
        quality = quality_raw if quality_raw is not None else round(depth, 3)
        completeness = completeness_raw if completeness_raw is not None else round(
            coverage, 3
        )

        report = {
            "data_source_used": data_source_used,
            "data_quality_score": quality,
            "data_completeness": completeness,
            "data_coverage": coverage,
        }
        report["confidence"] = confidence_level(report)
        report["data_refreshed"] = not needs_refresh(rows) if rows else False

        return report

    @staticmethod
    def _mean(values) -> Optional[float]:
        present = [v for v in values if v is not None]
        return sum(present) / len(present) if present else None

    def _market_edge(self, ticker: str, dcf_value: Optional[float]) -> dict:
        """Current price, market cap and valuation gap used for opportunity
        detection.

        The DCF value is company-total, so the margin of safety is computed
        against the total market cap (shares already priced in). Comparing
        the total DCF to the per-share price — as done before — produced a
        meaningless ~100% margin for every listed company.
        """
        price = self._safe_market(self._market.get_current_price, ticker)
        market_cap = self._safe_market(self._market.get_market_cap, ticker)
        margin = None
        if dcf_value and market_cap is not None and market_cap > 0:
            margin = (dcf_value - market_cap) / dcf_value
        return {
            "current_price": price,
            "market_cap": market_cap,
            "dcf_margin_of_safety": margin,
        }

    def _safe_market(self, getter, ticker: str) -> Optional[float]:
        try:
            value = getter(ticker)
            return value
        except Exception:  # noqa: BLE001
            return None

    def _gross_margins(
        self, rows: list[NormalizedFinancials], years: int = 5
    ) -> list[float]:
        margins: list[float] = []
        for row in rows[:years]:
            if row.revenue and row.cogs is not None and row.revenue != 0:
                margins.append((row.revenue - row.cogs) / row.revenue)
        return margins

    def _wacc(self, ticker: str, financials: NormalizedFinancials) -> Optional[float]:
        try:
            market_cap = self._market.get_market_cap(ticker)
            debt = financials.total_debt
            if market_cap is None or debt is None:
                return None
            total_cap = market_cap + debt
            weight_debt = debt / total_cap if total_cap != 0 else 0.5
            weight_equity = 1.0 - weight_debt

            beta = self._safe_market(self._market.get_beta, ticker) or 1.0
            cost_equity = self._risk_free_rate + beta * (
                self._market_return - self._risk_free_rate
            )

            if financials.interest_expense is not None and debt != 0:
                cost_debt = abs(financials.interest_expense) / debt
            else:
                cost_debt = DEFAULT_COST_OF_DEBT

            tax_rate = _sanitize_tax_rate(
                _effective_tax_rate(financials), self._default_tax_rate
            )
            return weight_equity * cost_equity + weight_debt * cost_debt * (
                1 - tax_rate
            )
        except Exception:  # noqa: BLE001
            return None
