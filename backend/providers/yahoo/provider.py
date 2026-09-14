from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from backend.domain.entities.financials import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
)
from backend.domain.interfaces.provider import FinancialDataProvider, MarketDataProvider


class YahooFinanceProvider(FinancialDataProvider, MarketDataProvider):
    def __init__(self):
        self._cache: dict[str, yf.Ticker] = {}

    def _get_ticker(self, ticker: str) -> yf.Ticker:
        if ticker not in self._cache:
            self._cache[ticker] = yf.Ticker(ticker)
        return self._cache[ticker]

    @staticmethod
    def _is_nan(value) -> bool:
        try:
            return bool(np.isnan(value))
        except (TypeError, ValueError):
            return False

    def _safe_val(self, series, index=0):
        try:
            val = series.iloc[index]
            if self._is_nan(val):
                return None
            return val
        except (IndexError, AttributeError, KeyError, TypeError):
            return None

    def _get(self, df: pd.DataFrame, name: str, index: int = 0):
        """Read a single row label; missing labels degrade to None instead of
        raising KeyError (some statements omit rows like Operating Income)."""
        try:
            return self._safe_val(df.loc[name], index)
        except (KeyError, IndexError, AttributeError, TypeError):
            return None

    def _pick(self, df: pd.DataFrame, candidates: list[str], index: int = 0):
        for name in candidates:
            try:
                val = df.loc[name].iloc[index]
                if self._is_nan(val):
                    continue
                return val
            except (KeyError, IndexError, AttributeError, TypeError):
                continue
        return None

    def get_income_statement(
        self, ticker: str, year_index: int = 0
    ) -> Optional[IncomeStatement]:
        t = self._get_ticker(ticker)
        try:
            ism = t.income_stmt
            return IncomeStatement(
                revenue=self._get(ism, "Total Revenue", year_index),
                cogs=self._get(ism, "Cost Of Revenue", year_index),
                gross_profit=self._get(ism, "Gross Profit", year_index),
                operating_income=self._get(ism, "Operating Income", year_index),
                ebit=self._get(ism, "Operating Income", year_index),
                ebitda=self._pick(ism, ["EBITDA"], year_index),
                net_income=self._get(ism, "Net Income", year_index),
                interest_expense=self._get(ism, "Interest Expense", year_index),
                tax_provision=self._get(ism, "Tax Provision", year_index),
                pretax_income=self._get(ism, "Pretax Income", year_index),
            )
        except (AttributeError, TypeError):
            return None

    def get_balance_sheet(
        self, ticker: str, year_index: int = 0
    ) -> Optional[BalanceSheet]:
        t = self._get_ticker(ticker)
        try:
            bs = t.balance_sheet
            return BalanceSheet(
                total_assets=self._get(bs, "Total Assets", year_index),
                total_liabilities=self._get(
                    bs, "Total Liabilities Net Minority Interest", year_index
                ),
                total_debt=self._get(bs, "Total Debt", year_index),
                cash_and_equivalents=self._get(
                    bs, "Cash And Cash Equivalents", year_index
                ),
                working_capital=self._get(bs, "Working Capital", year_index),
                retained_earnings=self._get(bs, "Retained Earnings", year_index),
                stockholders_equity=self._pick(
                    bs,
                    [
                        "Stockholders Equity",
                        "Common Stock Equity",
                        "Total Equity Gross Minority Interest",
                    ],
                    year_index,
                ),
            )
        except (AttributeError, TypeError):
            return None

    def get_cash_flow(
        self, ticker: str, year_index: int = 0
    ) -> Optional[CashFlowStatement]:
        t = self._get_ticker(ticker)
        try:
            cf = t.cashflow
            capex = self._get(cf, "Capital Expenditure", year_index)
            return CashFlowStatement(
                operating_cash_flow=self._pick(
                    cf,
                    [
                        "Operating Cash Flow",
                        "Cash Flow From Continuing Operating Activities",
                        "Total Cash From Operating Activities",
                    ],
                    year_index,
                ),
                capital_expenditure=abs(capex) if capex is not None else None,
                free_cash_flow=self._pick(cf, ["Free Cash Flow"], year_index),
                depreciation_amortization=self._pick(
                    cf,
                    [
                        "Depreciation And Amortization",
                        "Depreciation Amortization Depletion",
                    ],
                    year_index,
                ),
                dividends_paid=self._pick(
                    cf,
                    [
                        "Dividends Paid",
                        "Common Stock Dividends Paid",
                        "Cash Dividends Paid",
                    ],
                    year_index,
                ),
                repurchase_of_stock=self._pick(
                    cf,
                    [
                        "Repurchase Of Capital Stock",
                        "Stock Repurchased",
                        "Repurchase Of Common Stock",
                    ],
                    year_index,
                ),
            )
        except (KeyError, AttributeError, TypeError):
            return None

    def get_market_cap(self, ticker: str) -> Optional[float]:
        return self._get_ticker(ticker).info.get("marketCap")

    def get_enterprise_value(self, ticker: str) -> Optional[float]:
        return self._get_ticker(ticker).info.get("enterpriseValue")

    def get_current_price(self, ticker: str) -> Optional[float]:
        t = self._get_ticker(ticker)
        hist = t.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return None

    def get_beta(self, ticker: str) -> Optional[float]:
        return self._get_ticker(ticker).info.get("beta")

    def get_company_name(self, ticker: str) -> Optional[str]:
        info = self._get_ticker(ticker).info
        return info.get("longName") or info.get("shortName")

    def get_shares_outstanding(self, ticker: str) -> Optional[int]:
        return self._get_ticker(ticker).info.get("sharesOutstanding")

    def get_eps(self, ticker: str, year_index: int = 0) -> Optional[float]:
        """Diluted EPS for the requested annual period.

        Prefers Yahoo's reported 'Diluted EPS' row; falls back to
        net income / diluted weighted-average shares so the EPS basis on
        this side matches an as-reported fiscal year (not the current share
        count)."""
        try:
            ism = self._get_ticker(ticker).income_stmt
            eps = self._pick(ism, ["Diluted EPS", "Basic EPS"], year_index)
            if eps is not None:
                return float(eps)
            ni = self._get(ism, "Net Income", year_index)
            shares = self._pick(
                ism, ["Diluted Average Shares", "Basic Average Shares"], year_index
            )
            if ni is not None and shares:
                return float(ni) / float(shares)
        except (KeyError, AttributeError, TypeError):
            pass
        return None

    def get_fiscal_years(self, ticker: str) -> list[int]:
        """Fiscal years covered by the annual income statement, most recent first."""
        t = self._get_ticker(ticker)
        try:
            cols = t.income_stmt.columns
            years = sorted(
                {c.year for c in cols if getattr(c, "year", None)}, reverse=True
            )
            if years:
                return years
        except (KeyError, AttributeError, TypeError):
            pass
        return []

    def get_fiscal_year_end_dates(self, ticker: str) -> list[dict]:
        """Fiscal periods of the annual income statement, newest first.

        Each entry has 'year' (Yahoo's fiscal-year label) and 'end_date' (the
        actual fiscal-period-end date), letting callers anchor on the *period*
        rather than the label."""
        t = self._get_ticker(ticker)
        try:
            cols = t.income_stmt.columns
            entries = []
            for col in cols:
                if not getattr(col, "year", None):
                    continue
                entries.append(
                    {
                        "year": int(col.year),
                        "end_date": col.date()
                        if hasattr(col, "date")
                        else pd.Timestamp(col),
                    }
                )
            entries.sort(key=lambda e: e["end_date"], reverse=True)
            return entries
        except (KeyError, AttributeError, TypeError):
            return []

    def get_risk_free_rate(self) -> float:
        try:
            treasury = yf.Ticker("^TNX")
            rate = treasury.info.get("regularMarketPrice", 4.0)
            return rate / 100.0
        except Exception:
            return 0.04

    def get_effective_tax_rate(self, ticker: str, year_index: int = 0) -> float:
        ism = self.get_income_statement(ticker, year_index)
        if (
            ism
            and ism.tax_provision is not None
            and ism.pretax_income
            and ism.pretax_income != 0
        ):
            return ism.tax_provision / ism.pretax_income
        return 0.21

    def get_cost_of_equity(self, ticker: str, market_return: float = 0.10) -> float:
        beta = self.get_beta(ticker) or 1.0
        rf = self.get_risk_free_rate()
        return rf + beta * (market_return - rf)

    def get_cost_of_debt(self, ticker: str) -> float:
        ism = self.get_income_statement(ticker)
        bs = self.get_balance_sheet(ticker)
        interest = ism.interest_expense if ism else None
        debt = bs.total_debt if bs else None
        if interest is not None and debt is not None and debt != 0:
            return interest / debt
        return 0.05

    def get_wacc(self, ticker: str) -> float:
        try:
            mcap = self.get_market_cap(ticker)
            bs = self.get_balance_sheet(ticker)
            debt = bs.total_debt if bs else None
            if mcap is None or debt is None:
                return 0.08
            total_cap = mcap + debt
            wd = debt / total_cap if total_cap != 0 else 0.5
            we = 1.0 - wd

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
            return 0.08

    def get_financials(self, ticker: str, year_index: int = 0) -> Optional[object]:
        """Return an object with financial attributes for comparison.
        This method is intended for use in scripts like compare_sources.py.
        ``year_index`` selects the fiscal year column (0 = most recent).
        """
        class _Financials:
            def __init__(self):
                self.revenue: Optional[float] = None
                self.net_income: Optional[float] = None
                self.total_assets: Optional[float] = None
                self.total_liabilities: Optional[float] = None
                self.operating_cash_flow: Optional[float] = None
                self.capital_expenditure: Optional[float] = None  # positive
                self.shareholders_equity: Optional[float] = None
                self.diluted_eps: Optional[float] = None
                self.free_cash_flow: Optional[float] = None
                self.fiscal_year: Optional[int] = None

        try:
            ticker_obj = self._get_ticker(ticker)
            income = self.get_income_statement(ticker, year_index)
            balance = self.get_balance_sheet(ticker, year_index)
            cash_flow = self.get_cash_flow(ticker, year_index)
            shares_outstanding = self.get_shares_outstanding(ticker)

            if not any([income, balance, cash_flow]):
                return None

            fin = _Financials()
            if income:
                fin.revenue = float(income.revenue) if income.revenue is not None else None
                fin.net_income = float(income.net_income) if income.net_income is not None else None
            if balance:
                fin.total_assets = float(balance.total_assets) if balance.total_assets is not None else None
                fin.total_liabilities = float(balance.total_liabilities) if balance.total_liabilities is not None else None
                fin.shareholders_equity = float(balance.stockholders_equity) if balance.stockholders_equity is not None else None
            if cash_flow:
                fin.operating_cash_flow = float(cash_flow.operating_cash_flow) if cash_flow.operating_cash_flow is not None else None
                capex = cash_flow.capital_expenditure
                if capex is not None:
                    fin.capital_expenditure = abs(float(capex))
                fin.free_cash_flow = float(cash_flow.free_cash_flow) if cash_flow.free_cash_flow is not None else None
            # Calculate diluted EPS (as-reported fiscal-year basis)
            fin.diluted_eps = self.get_eps(ticker, year_index)
            # Attempt to get fiscal year (matching the selected column)
            try:
                entries = self.get_fiscal_year_end_dates(ticker)
                if entries and year_index < len(entries):
                    fin.fiscal_year = int(entries[year_index]["year"])
            except Exception:
                pass
            return fin
        except Exception:
            return None