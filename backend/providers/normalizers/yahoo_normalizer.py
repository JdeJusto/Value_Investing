"""Adapter: Yahoo Finance raw data → NormalizedFinancials."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
    RawFinancialsYear,
)
from backend.providers.normalizers.base import FinancialNormalizer


class YahooNormalizer(FinancialNormalizer):
    """Normalizes statements returned by ``YahooFinanceProvider``."""

    @property
    def source(self) -> ProviderName:
        return ProviderName.YAHOO

    def normalize(self, raw: RawFinancialsYear) -> NormalizedFinancials | None:
        income, balance, cash_flow = raw.income, raw.balance, raw.cash_flow
        if income is None and balance is None and cash_flow is None:
            return None

        revenue = income.revenue if income else None
        ebit = income.ebit if income else None
        operating_income = income.operating_income if income else None
        net_income = income.net_income if income else None
        depreciation = cash_flow.depreciation_amortization if cash_flow else None
        operating_cash_flow = cash_flow.operating_cash_flow if cash_flow else None
        capital_expenditure = cash_flow.capital_expenditure if cash_flow else None

        ebitda = income.ebitda if income and income.ebitda is not None else None
        if ebitda is None and ebit is not None and depreciation is not None:
            ebitda = ebit + depreciation

        free_cash_flow = cash_flow.free_cash_flow if cash_flow else None
        if (
            free_cash_flow is None
            and operating_cash_flow is not None
            and capital_expenditure is not None
        ):
            free_cash_flow = operating_cash_flow - capital_expenditure

        return NormalizedFinancials(
            ticker=raw.ticker,
            fiscal_year=raw.year,
            revenue=revenue,
            cogs=income.cogs if income else None,
            gross_profit=income.gross_profit if income else None,
            operating_income=operating_income,
            ebit=ebit,
            ebitda=ebitda,
            net_income=net_income,
            interest_expense=income.interest_expense if income else None,
            tax_provision=income.tax_provision if income else None,
            pretax_income=income.pretax_income if income else None,
            total_assets=balance.total_assets if balance else None,
            total_liabilities=balance.total_liabilities if balance else None,
            total_debt=balance.total_debt if balance else None,
            cash_and_equivalents=balance.cash_and_equivalents if balance else None,
            working_capital=balance.working_capital if balance else None,
            retained_earnings=balance.retained_earnings if balance else None,
            stockholders_equity=balance.stockholders_equity if balance else None,
            operating_cash_flow=operating_cash_flow,
            capital_expenditure=capital_expenditure,
            free_cash_flow=free_cash_flow,
            depreciation_amortization=depreciation,
            dividends_paid=cash_flow.dividends_paid if cash_flow else None,
            repurchase_of_stock=cash_flow.repurchase_of_stock if cash_flow else None,
            working_capital_change=(
                cash_flow.working_capital_change if cash_flow else None
            ),
            shares_outstanding=(
                int(raw.shares_outstanding) if raw.shares_outstanding else None
            ),
            source=self.source,
            loaded_at=datetime.now(timezone.utc),
        )
