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

    def _safe_val(self, series, index=0):
        try:
            val = series.iloc[index]
            if isinstance(val, float) and np.isnan(val):
                return None
            return val
        except (IndexError, AttributeError, KeyError, TypeError):
            return None

    def _pick(self, df: pd.DataFrame, candidates: list[str], index: int = 0):
        for name in candidates:
            try:
                val = df.loc[name].iloc[index]
                if isinstance(val, float) and np.isnan(val):
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
                revenue=self._safe_val(ism.loc["Total Revenue"], year_index),
                cogs=self._safe_val(ism.loc["Cost Of Revenue"], year_index),
                gross_profit=self._safe_val(ism.loc["Gross Profit"], year_index),
                operating_income=self._safe_val(
                    ism.loc["Operating Income"], year_index
                ),
                ebit=self._safe_val(ism.loc["Operating Income"], year_index),
                ebitda=self._pick(ism, ["EBITDA"], year_index),
                net_income=self._safe_val(ism.loc["Net Income"], year_index),
                interest_expense=self._safe_val(
                    ism.loc["Interest Expense"], year_index
                ),
                tax_provision=self._safe_val(ism.loc["Tax Provision"], year_index),
                pretax_income=self._safe_val(ism.loc["Pretax Income"], year_index),
            )
        except (KeyError, AttributeError, TypeError):
            return None

    def get_balance_sheet(
        self, ticker: str, year_index: int = 0
    ) -> Optional[BalanceSheet]:
        t = self._get_ticker(ticker)
        try:
            bs = t.balance_sheet
            return BalanceSheet(
                total_assets=self._safe_val(bs.loc["Total Assets"], year_index),
                total_liabilities=self._safe_val(
                    bs.loc["Total Liabilities Net Minority Interest"], year_index
                ),
                total_debt=self._safe_val(bs.loc["Total Debt"], year_index),
                cash_and_equivalents=self._safe_val(
                    bs.loc["Cash And Cash Equivalents"], year_index
                ),
                working_capital=self._safe_val(bs.loc["Working Capital"], year_index),
                retained_earnings=self._safe_val(
                    bs.loc["Retained Earnings"], year_index
                ),
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
        except (KeyError, AttributeError, TypeError):
            return None

    def get_cash_flow(
        self, ticker: str, year_index: int = 0
    ) -> Optional[CashFlowStatement]:
        t = self._get_ticker(ticker)
        try:
            cf = t.cashflow
            capex = self._safe_val(cf.loc["Capital Expenditure"], year_index)
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
        return self._get_ticker(ticker).info.get("longName") or self._get_ticker(
            ticker
        ).info.get("shortName")

    def get_shares_outstanding(self, ticker: str) -> Optional[int]:
        return self._get_ticker(ticker).info.get("sharesOutstanding")

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
            cost_debt = self.get_cost_of_debt(ticker)
            tax = self.get_effective_tax_rate(ticker)
            cost_equity = self.get_cost_of_equity(ticker)
            return we * cost_equity + wd * cost_debt * (1 - tax)
        except Exception:
            return 0.08
