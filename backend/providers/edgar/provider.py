from __future__ import annotations

from typing import TYPE_CHECKING

from backend.domain.entities.financials import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
)
from backend.domain.interfaces.provider import FinancialDataProvider

if TYPE_CHECKING:
    # edgartools is imported lazily at first use (heavy); the annotations
    # only need the name at type-check time.
    from edgar import Company


class EdgarProvider(FinancialDataProvider):
    def __init__(self, email: str, name: str):
        # edgartools is heavy (~2.7 s import) and is only needed when EDGAR
        # fallback data is actually fetched — nothing imports it here, so
        # building the pipeline for FDB-backed commands never pays the cost.
        self._email = email
        self._name = name
        self._identity_set = False
        self._companies: dict[str, Company] = {}
        self._financials: dict[str, object] = {}

    def _set_identity(self) -> None:
        if self._identity_set:
            return
        from edgar import set_identity

        set_identity(f"{self._name} {self._email}")
        self._identity_set = True

    def _get_company(self, ticker: str) -> Company | None:
        if ticker not in self._companies:
            try:
                from edgar import Company

                self._set_identity()
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
    ) -> IncomeStatement | None:
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
    ) -> BalanceSheet | None:
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
    ) -> CashFlowStatement | None:
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

    def get_total_assets(self, ticker: str) -> float | None:
        bs = self.get_balance_sheet(ticker)
        return bs.total_assets if bs else None

    def get_total_liabilities(self, ticker: str) -> float | None:
        bs = self.get_balance_sheet(ticker)
        return bs.total_liabilities if bs else None

    def get_stockholders_equity(self, ticker: str) -> float | None:
        bs = self.get_balance_sheet(ticker)
        return bs.stockholders_equity if bs else None

    def get_financials(self, ticker: str) -> object | None:
        """Return an object with financial attributes for comparison.
        This method is intended for use in scripts like compare_sources.py.
        """
        class _Financials:
            def __init__(self):
                self.revenue: float | None = None
                self.net_income: float | None = None
                self.total_assets: float | None = None
                self.total_liabilities: float | None = None
                self.operating_cash_flow: float | None = None
                self.capital_expenditure: float | None = None  # positive
                self.shareholders_equity: float | None = None
                self.diluted_eps: float | None = None
                self.free_cash_flow: float | None = None
                self.fiscal_year: int | None = None

        try:
            fins = self._get_financials(ticker)
            if not fins:
                return None

            fin = _Financials()
            fin.revenue = float(fins.get_revenue(0)) if fins.get_revenue(0) is not None else None
            fin.net_income = float(fins.get_net_income(0)) if fins.get_net_income(0) is not None else None
            fin.total_assets = float(fins.get_total_assets(0)) if fins.get_total_assets(0) is not None else None
            fin.total_liabilities = float(fins.get_total_liabilities(0)) if fins.get_total_liabilities(0) is not None else None
            fin.operating_cash_flow = float(fins.get_operating_cash_flow(0)) if fins.get_operating_cash_flow(0) is not None else None
            capex = fins.get_capital_expenditures(0)
            if capex is not None:
                fin.capital_expenditure = abs(float(capex))
            fin.free_cash_flow = float(fins.get_free_cash_flow(0)) if fins.get_free_cash_flow(0) is not None else None
            # Calculate diluted EPS if possible (EDGAR doesn't have shares outstanding directly in the financials object?)
            # We'll leave it as None for now.
            # Attempt to get fiscal year (not directly available; we could try to infer from filings? skip)
            return fin
        except Exception:
            return None
