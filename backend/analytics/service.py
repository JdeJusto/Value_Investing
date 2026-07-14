from typing import Optional

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
from backend.analytics.ratios.roe import RoeCalculator
from backend.analytics.ratios.roic import IncrementalRoicCalculator, RoicCalculator
from backend.analytics.scoring.altman_z import AltmanZScoreCalculator
from backend.analytics.scoring.composite import CompositeScoreCalculator
from backend.analytics.scoring.piotroski import PiotroskiFScoreCalculator
from backend.analytics.valuation.dcf import DcfCalculator
from backend.domain.entities.financials import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
)
from backend.domain.interfaces.provider import FinancialDataProvider, MarketDataProvider


def _merge(obj, *others):
    if obj is None and not others:
        return None
    if obj is None:
        obj = type(others[0])()
    for other in others:
        if other is None:
            continue
        for field in obj.__dataclass_fields__:
            if getattr(obj, field) is None:
                val = getattr(other, field, None)
                if val is not None:
                    setattr(obj, field, val)
    return obj


class CompanyAnalysisService:
    def __init__(
        self,
        financial_providers: list[FinancialDataProvider],
        market_provider: MarketDataProvider,
    ):
        self._financial_providers = financial_providers
        self._market = market_provider

    def _get_income(self, ticker: str, year_index: int = 0) -> Optional[IncomeStatement]:
        result = None
        for p in self._financial_providers:
            try:
                ism = p.get_income_statement(ticker, year_index)
                if ism is not None:
                    result = _merge(result, ism)
            except Exception:
                continue
        if result is not None and result.revenue is None and result.net_income is None:
            return None
        return result

    def _get_balance(self, ticker: str, year_index: int = 0) -> Optional[BalanceSheet]:
        result = None
        for p in self._financial_providers:
            try:
                bs = p.get_balance_sheet(ticker, year_index)
                if bs is not None:
                    result = _merge(result, bs)
            except Exception:
                continue
        return result

    def _get_cash_flow(self, ticker: str, year_index: int = 0) -> Optional[CashFlowStatement]:
        result = None
        for p in self._financial_providers:
            try:
                cf = p.get_cash_flow(ticker, year_index)
                if cf is not None:
                    result = _merge(result, cf)
            except Exception:
                continue
        return result

    def _get_effective_tax_rate(self, ticker: str) -> float:
        for p in self._financial_providers:
            if hasattr(p, "get_effective_tax_rate"):
                try:
                    tr = p.get_effective_tax_rate(ticker)
                    if tr is not None:
                        return tr
                except Exception:
                    continue
        return 0.21

    def _get_wacc(self, ticker: str) -> float:
        for p in self._financial_providers:
            if hasattr(p, "get_wacc"):
                try:
                    w = p.get_wacc(ticker)
                    if w is not None:
                        return w
                except Exception:
                    continue
        return 0.08

    def analyze(self, ticker: str) -> Optional[dict]:
        is0 = self._get_income(ticker, 0)
        is1 = self._get_income(ticker, 1)
        bs0 = self._get_balance(ticker, 0)
        bs1 = self._get_balance(ticker, 1)
        cf0 = self._get_cash_flow(ticker, 0)

        if is0 is None and bs0 is None and cf0 is None:
            return None

        market_cap = self._market.get_market_cap(ticker)
        ev = self._market.get_enterprise_value(ticker)

        equity = None
        if bs0 and bs0.stockholders_equity is not None:
            equity = bs0.stockholders_equity
        elif bs0 and bs0.total_assets is not None and bs0.total_liabilities is not None:
            equity = bs0.total_assets - bs0.total_liabilities

        net_income = is0.net_income if is0 else None
        revenue = is0.revenue if is0 else None
        op_income = is0.operating_income if is0 else None
        ebit = is0.ebit if is0 else None
        cash = bs0.cash_and_equivalents if bs0 else None
        debt = bs0.total_debt if bs0 else None
        assets = bs0.total_assets if bs0 else None
        liab = bs0.total_liabilities if bs0 else None
        wc = bs0.working_capital if bs0 else None
        re = bs0.retained_earnings if bs0 else None
        fcf = cf0.free_cash_flow if cf0 else None
        cfo = cf0.operating_cash_flow if cf0 else None
        da = cf0.depreciation_amortization if cf0 else None
        dividends = cf0.dividends_paid if cf0 else None
        buybacks = cf0.repurchase_of_stock if cf0 else None
        maintenance_capex = cf0.capital_expenditure if cf0 else None

        ebitda = None
        if is0 and is0.ebitda is not None:
            ebitda = is0.ebitda
        elif ebit is not None and da is not None:
            ebitda = ebit + da

        gross_margins_list = self._get_gross_margins(ticker)
        tax_rate = self._get_effective_tax_rate(ticker)
        wacc = self._get_wacc(ticker)
        fcf_from_cf = cf0.free_cash_flow if cf0 else None

        roa_current = None
        roa_prior = None
        if net_income is not None and assets is not None and assets != 0:
            roa_current = net_income / assets
        if is1 and is1.net_income is not None and bs1 and bs1.total_assets is not None and bs1.total_assets != 0:
            roa_prior = is1.net_income / bs1.total_assets

        invested_capital = None
        if debt is not None and equity is not None:
            invested_capital = debt + equity - (cash or 0)

        result = {
            "ticker": ticker,
            "market_cap": market_cap,
            "revenue": revenue,
            "net_income": net_income,
            "fcf": fcf,
        }

        result["roe"] = RoeCalculator().calculate(net_income=net_income, equity=equity)
        result["pb"] = PbCalculator().calculate(market_cap=market_cap, equity=equity)
        result["roic"] = RoicCalculator().calculate(
            ebit=ebit, tax_rate=tax_rate, total_debt=debt, equity=equity, cash=cash,
        )
        result["incremental_roic"] = IncrementalRoicCalculator().calculate(
            ebit_current=ebit,
            ebit_prior=is1.ebit if is1 else None,
            tax_rate=tax_rate,
            debt_current=debt,
            debt_prior=bs1.total_debt if bs1 else None,
            equity_current=equity,
            equity_prior=(
                bs1.stockholders_equity
                if bs1 and bs1.stockholders_equity is not None
                else (bs1.total_assets - bs1.total_liabilities if bs1 and bs1.total_assets and bs1.total_liabilities else None)
            ),
            cash_current=cash,
            cash_prior=bs1.cash_and_equivalents if bs1 else None,
        )
        result["operating_margin"] = OperatingMarginCalculator().calculate(
            operating_income=op_income, revenue=revenue,
        )
        result["net_margin"] = NetMarginCalculator().calculate(
            net_income=net_income, revenue=revenue,
        )
        result["fcf_yield"] = FcfYieldCalculator().calculate(
            free_cash_flow=fcf_from_cf, market_cap=market_cap,
        )
        result["ev_ebit"] = EvEbitCalculator().calculate(
            enterprise_value=ev, ebit=ebit,
        )
        result["acquirers_multiple"] = result["ev_ebit"]
        result["owner_earnings"] = OwnerEarningsCalculator().calculate(
            net_income=net_income, depreciation=da,
            maintenance_capex=maintenance_capex,
            working_capital_change=cf0.working_capital_change if cf0 else None,
        )
        result["piotroski_fscore"] = PiotroskiFScoreCalculator().calculate(
            roa_current=roa_current, roa_prior=roa_prior,
            cfo_current=cfo, net_income_current=net_income,
            total_assets_current=assets,
            total_assets_prior=bs1.total_assets if bs1 else None,
            total_debt_current=debt, total_debt_prior=bs1.total_debt if bs1 else None,
            working_capital_current=wc,
            working_capital_prior=bs1.working_capital if bs1 else None,
            revenue_current=revenue, revenue_prior=is1.revenue if is1 else None,
            cogs_current=is0.cogs if is0 else None,
            cogs_prior=is1.cogs if is1 else None,
        )
        result["altman_zscore"] = AltmanZScoreCalculator().calculate(
            working_capital=wc, total_assets=assets,
            retained_earnings=re, ebit=ebit,
            market_cap=market_cap, total_liabilities=liab, revenue=revenue,
        )
        result["net_debt_to_ebitda"] = NetDebtToEbitdaCalculator().calculate(
            total_debt=debt, cash=cash, ebitda=ebitda,
        )
        result["interest_coverage"] = InterestCoverageCalculator().calculate(
            ebit=ebit, interest_expense=is0.interest_expense if is0 else None,
        )
        result["gross_margin_stability"] = GrossMarginStabilityCalculator().calculate(
            gross_margins=gross_margins_list,
        )
        result["fcf_conversion"] = FcfConversionCalculator().calculate(
            free_cash_flow=fcf_from_cf, net_income=net_income,
        )
        result["croic"] = CroicCalculator().calculate(
            free_cash_flow=fcf_from_cf, invested_capital=invested_capital,
        )
        result["dcf_value"] = DcfCalculator().calculate(
            free_cash_flow=fcf_from_cf, wacc=wacc,
        )
        result["shareholder_yield"] = ShareholderYieldCalculator().calculate(
            dividends=dividends, buybacks=buybacks, market_cap=market_cap,
        )
        result["score"] = CompositeScoreCalculator().calculate(
            roe=result["roe"], pb=result["pb"],
            fcf_yield=result["fcf_yield"],
            operating_margin=result["operating_margin"],
        )

        return result

    def _get_gross_margins(self, ticker: str, years: int = 5) -> list:
        for p in self._financial_providers:
            if hasattr(p, "get_income_statement"):
                margins = []
                for i in range(years):
                    ism = p.get_income_statement(ticker, i)
                    if ism and ism.revenue and ism.cogs is not None and ism.revenue != 0:
                        margins.append((ism.revenue - ism.cogs) / ism.revenue)
                    else:
                        break
                if len(margins) > 1:
                    return margins
                break
        return []
