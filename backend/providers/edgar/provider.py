from typing import Optional

from edgar import Company, set_identity

from backend.domain.entities.financials import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
)
from backend.domain.interfaces.provider import FinancialDataProvider


class EdgarProvider(FinancialDataProvider):
    def __init__(self, email: str, name: str):
        set_identity(f"{name} {email}")
        self._companies: dict[str, Company] = {}
        self._financials: dict[str, object] = {}

    def _get_company(self, ticker: str) -> Optional[Company]:
        if ticker not in self._companies:
            try:
                self._companies[ticker] = Company(ticker)
            except Exception:
                return None
        return self._companies[ticker]

    def _get_financials(self, ticker: str):
        if ticker not in self._financials:
            company = self._get_company(ticker)
            if company:
                try:
                    self._financials[ticker] = company.get_financials()
                except Exception:
                    self._financials[ticker] = None
        return self._financials.get(ticker)

    def get_income_statement(
        self, ticker: str, year_index: int = 0
    ) -> Optional[IncomeStatement]:
        fins = self._get_financials(ticker)
        if fins is None:
            return None
        try:
            ebit = fins.get_operating_income(year_index)
            return IncomeStatement(
                revenue=fins.get_revenue(year_index),
                ebit=ebit,
                operating_income=ebit,
                net_income=fins.get_net_income(year_index),
            )
        except Exception:
            return None

    def get_balance_sheet(
        self, ticker: str, year_index: int = 0
    ) -> Optional[BalanceSheet]:
        fins = self._get_financials(ticker)
        if fins is None:
            return None
        try:
            return BalanceSheet(
                total_assets=fins.get_total_assets(year_index),
                total_liabilities=fins.get_total_liabilities(year_index),
                total_debt=None,
                stockholders_equity=fins.get_stockholders_equity(year_index),
            )
        except Exception:
            return None

    def get_cash_flow(
        self, ticker: str, year_index: int = 0
    ) -> Optional[CashFlowStatement]:
        fins = self._get_financials(ticker)
        if fins is None:
            return None
        try:
            capex = fins.get_capital_expenditures(year_index)
            return CashFlowStatement(
                operating_cash_flow=fins.get_operating_cash_flow(year_index),
                capital_expenditure=abs(capex) if capex is not None else None,
                free_cash_flow=fins.get_free_cash_flow(year_index),
            )
        except Exception:
            return None

    def get_total_assets(self, ticker: str) -> Optional[float]:
        bs = self.get_balance_sheet(ticker)
        return bs.total_assets if bs else None

    def get_total_liabilities(self, ticker: str) -> Optional[float]:
        bs = self.get_balance_sheet(ticker)
        return bs.total_liabilities if bs else None

    def get_stockholders_equity(self, ticker: str) -> Optional[float]:
        bs = self.get_balance_sheet(ticker)
        return bs.stockholders_equity if bs else None
