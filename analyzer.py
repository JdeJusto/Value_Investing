# analyzer.py - Híbrido yfinance + EDGAR con manejo robusto de None

from edgar import Company
import yfinance as yf
import pandas as pd
import numpy as np
from calculos.datos_basicos import (
    get_ticker, get_revenue, get_ebit, get_net_income, get_free_cash_flow,
    get_cfo, get_capex_total, get_total_assets, get_total_liabilities,
    get_total_debt, get_cash_and_equivalents, get_retained_earnings,
    get_working_capital, get_interest_expense, get_effective_tax_rate,
    get_market_cap, get_enterprise_value, get_current_price, get_shares_outstanding,
    get_beta, get_risk_free_rate, get_cost_of_equity, get_wacc,
    get_fcf_growth_rate, get_historical_revenue, get_historical_ebit,
    get_depreciation_amortization, get_maintenance_capex, get_working_capital_change,
    get_cogs
)


class StockAnalyzer:
    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        try:
            self.company = Company(self.ticker)
            self.financials = self.company.get_financials()
        except Exception:
            self.company = None
            self.financials = None
        self.yf_ticker = get_ticker(self.ticker)
        self.market_data = self.yf_ticker.info

    # ------------------------------------------------------------
    # MÉTODOS AUXILIARES HÍBRIDOS (yfinance -> EDGAR)
    # ------------------------------------------------------------
    def _get_from_yfinance_or_edgar(self, yfinance_func, edgar_attr, year_index=0):
        try:
            val = yfinance_func(self.ticker, year_index)
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                return val
        except:
            pass
        if self.financials is not None:
            try:
                edgar_method = getattr(self.financials, edgar_attr, None)
                if edgar_method and callable(edgar_method):
                    val = edgar_method()
                    if val is not None and not (isinstance(val, float) and np.isnan(val)):
                        return val
            except:
                pass
        return None

    def _get_equity_from_edgar(self):
        if self.financials is not None:
            try:
                return self.financials.get_stockholders_equity()
            except:
                pass
        return None

    # ------------------------------------------------------------
    # MÉTRICAS (1 a 15)
    # ------------------------------------------------------------
    def get_roic(self, year_index=0):
        ebit = self._get_from_yfinance_or_edgar(get_ebit, 'get_operating_income', year_index)
        tax_rate = get_effective_tax_rate(self.ticker, year_index) or 0.21
        if ebit is None:
            return None
        nopat = ebit * (1 - tax_rate)

        total_debt = self._get_from_yfinance_or_edgar(get_total_debt, 'get_total_debt', year_index) or 0
        total_assets = self._get_from_yfinance_or_edgar(get_total_assets, 'get_total_assets', year_index)
        total_liabilities = self._get_from_yfinance_or_edgar(get_total_liabilities, 'get_total_liabilities', year_index)

        if total_assets is None or total_liabilities is None:
            equity = self._get_equity_from_edgar()
            if equity is not None:
                cash = get_cash_and_equivalents(self.ticker, year_index) or 0
                invested_capital = total_debt + equity - cash
                if invested_capital != 0:
                    return nopat / invested_capital
            return None
        equity = total_assets - total_liabilities
        cash = get_cash_and_equivalents(self.ticker, year_index) or 0
        invested_capital = total_debt + equity - cash
        if invested_capital == 0:
            return None
        return nopat / invested_capital

    def get_incremental_roic(self):
        try:
            nopat0 = self._get_nopat(0)
            nopat1 = self._get_nopat(1)
            ic0 = self._get_invested_capital(0)
            ic1 = self._get_invested_capital(1)
            if None in (nopat0, nopat1, ic0, ic1):
                return None
            delta_nopat = nopat0 - nopat1
            delta_ic = ic0 - ic1
            return delta_nopat / delta_ic if delta_ic != 0 else None
        except:
            return None

    def get_fcf_yield(self):
        fcf = self._get_from_yfinance_or_edgar(get_free_cash_flow, 'get_free_cash_flow')
        mcap = get_market_cap(self.ticker)
        if fcf and mcap:
            return fcf / mcap
        return None

    def get_ev_ebit(self):
        ev = get_enterprise_value(self.ticker)
        ebit = self._get_from_yfinance_or_edgar(get_ebit, 'get_operating_income')
        if ev and ebit and ebit != 0:
            return ev / ebit
        return None

    def get_owner_earnings(self):
        ni = self._get_from_yfinance_or_edgar(get_net_income, 'get_net_income')
        da = get_depreciation_amortization(self.ticker)
        maint_capex = get_maintenance_capex(self.ticker)
        wc_change = get_working_capital_change(self.ticker)
        if None in (ni, da, maint_capex):
            return None
        owner = ni + da - maint_capex
        if wc_change is not None:
            owner -= wc_change
        return owner

    def get_piotroski_fscore(self):
        try:
            roa0 = self._get_roa(0)
            roa1 = self._get_roa(1)
            cfo0 = get_cfo(self.ticker, 0)
            cfo1 = get_cfo(self.ticker, 1)
            ni0 = get_net_income(self.ticker, 0)
            assets0 = get_total_assets(self.ticker, 0)
            accruals = (cfo0 - ni0) / assets0 if (cfo0 and ni0 and assets0) else None
            debt0 = get_total_debt(self.ticker, 0) or 0
            debt1 = get_total_debt(self.ticker, 1) or 0
            lev0 = debt0 / assets0 if assets0 else None
            lev1 = debt1 / get_total_assets(self.ticker, 1) if get_total_assets(self.ticker, 1) else None
            wc0 = get_working_capital(self.ticker, 0) or 0
            wc1 = get_working_capital(self.ticker, 1) or 0
            liq0 = wc0 / assets0 if assets0 else None
            liq1 = wc1 / get_total_assets(self.ticker, 1) if get_total_assets(self.ticker, 1) else None
            rev0 = get_revenue(self.ticker, 0)
            cogs0 = get_cogs(self.ticker, 0)
            gm0 = (rev0 - cogs0) / rev0 if (rev0 and cogs0) else None
            rev1 = get_revenue(self.ticker, 1)
            cogs1 = get_cogs(self.ticker, 1)
            gm1 = (rev1 - cogs1) / rev1 if (rev1 and cogs1) else None
            at0 = rev0 / assets0 if (rev0 and assets0) else None
            at1 = rev1 / get_total_assets(self.ticker, 1) if (rev1 and get_total_assets(self.ticker, 1)) else None
            score = 0
            if roa0 and roa0 > 0: score += 1
            if cfo0 and cfo0 > 0: score += 1
            if roa0 and roa1 and roa0 > roa1: score += 1
            if accruals and accruals > 0: score += 1
            if lev0 and lev1 and lev0 < lev1: score += 1
            if liq0 and liq1 and liq0 > liq1: score += 1
            score += 1
            if gm0 and gm1 and gm0 > gm1: score += 1
            if at0 and at1 and at0 > at1: score += 1
            return score
        except Exception:
            return None

    def get_altman_zscore(self):
        wc = get_working_capital(self.ticker) or 0
        assets = self._get_from_yfinance_or_edgar(get_total_assets, 'get_total_assets')
        re = get_retained_earnings(self.ticker) or 0
        ebit = self._get_from_yfinance_or_edgar(get_ebit, 'get_operating_income') or 0
        mcap = get_market_cap(self.ticker) or 0
        liab = self._get_from_yfinance_or_edgar(get_total_liabilities, 'get_total_liabilities') or 0
        revenue = self._get_from_yfinance_or_edgar(get_revenue, 'get_revenue') or 0
        if None in (assets, liab, revenue):
            return None
        A = wc / assets
        B = re / assets
        C = ebit / assets
        D = mcap / liab if liab != 0 else 0
        E = revenue / assets
        z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
        return z

    def get_net_debt_to_ebitda(self):
        debt = get_total_debt(self.ticker) or 0
        cash = get_cash_and_equivalents(self.ticker) or 0
        ebitda = self._get_ebitda()
        if ebitda is None or ebitda == 0:
            return None
        net_debt = debt - cash
        return net_debt / ebitda

    def get_interest_coverage(self):
        ebit = self._get_from_yfinance_or_edgar(get_ebit, 'get_operating_income')
        interest = get_interest_expense(self.ticker)
        if ebit is None or interest is None or interest == 0:
            return None
        return ebit / interest

    def get_gross_margin_stability(self, years=5):
        margins = []
        try:
            rev_series = self.yf_ticker.income_stmt.loc["Total Revenue"]
            possible_cogs_names = ["Cost Of Revenue", "Cost of Revenue", "Cost of Goods Sold", "Cost of Sales"]
            cogs_series = None
            for name in possible_cogs_names:
                try:
                    cogs_series = self.yf_ticker.income_stmt.loc[name]
                    break
                except:
                    continue
            if cogs_series is None:
                return None
            for i in range(min(years, len(rev_series))):
                rev = rev_series.iloc[i]
                cogs = cogs_series.iloc[i]
                if rev and rev != 0 and cogs is not None:
                    margins.append((rev - cogs) / rev)
            if len(margins) > 1:
                return np.std(margins)
            return None
        except:
            return None

    def get_fcf_conversion(self):
        fcf = self._get_from_yfinance_or_edgar(get_free_cash_flow, 'get_free_cash_flow')
        ni = self._get_from_yfinance_or_edgar(get_net_income, 'get_net_income')
        if fcf and ni and ni != 0:
            return fcf / ni
        return None

    def get_croic(self):
        fcf = self._get_from_yfinance_or_edgar(get_free_cash_flow, 'get_free_cash_flow')
        ic = self._get_invested_capital(0)
        if fcf and ic and ic != 0:
            return fcf / ic
        return None

    def get_acquirers_multiple(self):
        return self.get_ev_ebit()

    def get_dcf_value(self, growth_rate=0.05, terminal_growth=0.02, years=5):
        try:
            fcf0 = self._get_from_yfinance_or_edgar(get_free_cash_flow, 'get_free_cash_flow')
            if fcf0 is None:
                return None
            wacc = get_wacc(self.ticker)
            if wacc is None or wacc <= terminal_growth:
                wacc = 0.08
            fcf_sum = 0
            for t in range(1, years+1):
                fcf_t = fcf0 * (1 + growth_rate) ** t
                fcf_sum += fcf_t / ((1 + wacc) ** t)
            terminal_fcf = fcf0 * (1 + growth_rate) ** years * (1 + terminal_growth)
            terminal_value = terminal_fcf / (wacc - terminal_growth)
            terminal_pv = terminal_value / ((1 + wacc) ** years)
            return fcf_sum + terminal_pv
        except:
            return None

    def get_shareholder_yield(self):
        t = self.yf_ticker
        try:
            dividends = t.cashflow.loc["Dividends Paid"].iloc[0] if "Dividends Paid" in t.cashflow.index else 0
            buybacks = t.cashflow.loc["Repurchase Of Capital Stock"].iloc[0] if "Repurchase Of Capital Stock" in t.cashflow.index else 0
        except:
            dividends = 0
            buybacks = 0
        mcap = get_market_cap(self.ticker)
        if mcap and mcap != 0:
            return -(dividends + buybacks) / mcap
        return None

    # ------------------------------------------------------------
    # MÉTODOS AUXILIARES PRIVADOS
    # ------------------------------------------------------------
    def _get_nopat(self, year_index):
        ebit = self._get_from_yfinance_or_edgar(get_ebit, 'get_operating_income', year_index)
        tax = get_effective_tax_rate(self.ticker, year_index) or 0.21
        if ebit is None:
            return None
        return ebit * (1 - tax)

    def _get_invested_capital(self, year_index):
        debt = self._get_from_yfinance_or_edgar(get_total_debt, 'get_total_debt', year_index) or 0
        assets = self._get_from_yfinance_or_edgar(get_total_assets, 'get_total_assets', year_index)
        liab = self._get_from_yfinance_or_edgar(get_total_liabilities, 'get_total_liabilities', year_index)
        if assets is None or liab is None:
            equity = self._get_equity_from_edgar()
            if equity is not None:
                cash = get_cash_and_equivalents(self.ticker, year_index) or 0
                return debt + equity - cash
            return None
        equity = assets - liab
        cash = get_cash_and_equivalents(self.ticker, year_index) or 0
        return debt + equity - cash

    def _get_ebitda(self):
        ebit = self._get_from_yfinance_or_edgar(get_ebit, 'get_operating_income')
        da = get_depreciation_amortization(self.ticker)
        if ebit is not None and da is not None:
            return ebit + da
        return None

    def _get_roa(self, year_index):
        ni = self._get_from_yfinance_or_edgar(get_net_income, 'get_net_income', year_index)
        assets = self._get_from_yfinance_or_edgar(get_total_assets, 'get_total_assets', year_index)
        if ni and assets and assets != 0:
            return ni / assets
        return None

    # ------------------------------------------------------------
    # MÉTRICAS ORIGINALES (con protección de None)
    # ------------------------------------------------------------
    def get_fundamentals(self):
        assets = get_total_assets(self.ticker)
        liab = get_total_liabilities(self.ticker)
        if assets is not None and liab is not None:
            equity = assets - liab
        else:
            equity = self._get_equity_from_edgar()
        net_income = self._get_from_yfinance_or_edgar(get_net_income, 'get_net_income')
        fcf = self._get_from_yfinance_or_edgar(get_free_cash_flow, 'get_free_cash_flow')
        revenue = self._get_from_yfinance_or_edgar(get_revenue, 'get_revenue')
        operating_income = self._get_from_yfinance_or_edgar(get_ebit, 'get_operating_income')
        market_cap = get_market_cap(self.ticker)
        return {
            "equity": equity,
            "net_income": net_income,
            "fcf": fcf,
            "revenue": revenue,
            "operating_income": operating_income,
            "market_cap": market_cap,
        }

    def compute_score(self, roe, pb, fcf_yield, operating_margin):
        score = 0
        if roe:
            score += roe * 0.25
        if pb and pb != 0:
            score += (1 / pb) * 0.25
        if fcf_yield:
            score += fcf_yield * 0.25
        if operating_margin:
            score += operating_margin * 0.25
        return score

    def compute_metrics(self, f):
        equity = f.get("equity")
        net_income = f.get("net_income")
        fcf = f.get("fcf")
        revenue = f.get("revenue")
        operating_income = f.get("operating_income")
        market_cap = f.get("market_cap")

        roe = None
        if net_income and equity and equity != 0:
            roe = net_income / equity

        pb = None
        if market_cap and equity and equity != 0:
            pb = market_cap / equity

        fcf_yield = None
        if fcf and market_cap:
            fcf_yield = fcf / market_cap

        operating_margin = None
        if revenue and operating_income:
            operating_margin = operating_income / revenue

        net_margin = None
        if revenue and net_income:
            net_margin = net_income / revenue

        score = self.compute_score(roe, pb, fcf_yield, operating_margin)

        return {
            "ticker": self.ticker,
            **f,
            "roe": roe,
            "pb": pb,
            "fcf_yield": fcf_yield,
            "operating_margin": operating_margin,
            "net_margin": net_margin,
            "score": score,
            "roic": self.get_roic(),
            "incremental_roic": self.get_incremental_roic(),
            "ev_ebit": self.get_ev_ebit(),
            "owner_earnings": self.get_owner_earnings(),
            "piotroski_fscore": self.get_piotroski_fscore(),
            "altman_zscore": self.get_altman_zscore(),
            "net_debt_to_ebitda": self.get_net_debt_to_ebitda(),
            "interest_coverage": self.get_interest_coverage(),
            "gross_margin_stability": self.get_gross_margin_stability(),
            "fcf_conversion": self.get_fcf_conversion(),
            "croic": self.get_croic(),
            "acquirers_multiple": self.get_acquirers_multiple(),
            "dcf_value": self.get_dcf_value(),
            "shareholder_yield": self.get_shareholder_yield(),
        }

    def analyze(self):
        fundamentals = self.get_fundamentals()
        return self.compute_metrics(fundamentals)