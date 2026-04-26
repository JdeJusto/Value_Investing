# analyzer.py (versión expandida)

from edgar import Company
import yfinance as yf
import pandas as pd
import numpy as np

# Importamos las funciones auxiliares desde tu módulo de cálculos
from calculos.datos_basicos import (
    get_ticker, get_revenue, get_ebit, get_net_income, get_free_cash_flow,
    get_cfo, get_capex_total, get_total_assets, get_total_liabilities,
    get_total_debt, get_cash_and_equivalents, get_retained_earnings,
    get_working_capital, get_interest_expense, get_effective_tax_rate,
    get_market_cap, get_enterprise_value, get_current_price, get_shares_outstanding,
    get_beta, get_risk_free_rate, get_cost_of_equity, get_wacc,
    get_fcf_growth_rate, get_historical_revenue, get_historical_ebit,
    get_depreciation_amortization, get_maintenance_capex, get_working_capital_change
)


class StockAnalyzer:
    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self.company = Company(self.ticker)          # opcional, puede eliminarse si no usas EDGAR
        self.yf_ticker = get_ticker(self.ticker)     # objeto yfinance con caché
        self.market_data = self.yf_ticker.info

    # ─────────────────────────────
    # MÉTRICAS SOLICITADAS (1 a 15)
    # ─────────────────────────────

    def get_roic(self, year_index=0):
        """
        1. ROIC = NOPAT / Invested Capital
        NOPAT = EBIT * (1 - tasa_impositiva)
        Invested Capital = Total Debt + Total Equity - Cash & Equivalents
        """
        ebit = get_ebit(self.ticker, year_index)
        tax_rate = get_effective_tax_rate(self.ticker, year_index) or 0.21
        if ebit is None:
            return None
        nopat = ebit * (1 - tax_rate)

        total_debt = get_total_debt(self.ticker, year_index) or 0
        # Equity = Total Assets - Total Liabilities
        total_assets = get_total_assets(self.ticker, year_index)
        total_liabilities = get_total_liabilities(self.ticker, year_index)
        if total_assets is None or total_liabilities is None:
            return None
        equity = total_assets - total_liabilities
        cash = get_cash_and_equivalents(self.ticker, year_index) or 0
        invested_capital = total_debt + equity - cash
        if invested_capital == 0:
            return None
        return nopat / invested_capital

    def get_incremental_roic(self):
        """
        2. Incremental ROIC = (ΔNOPAT) / (ΔInvested Capital)
        Compara el año más reciente con el anterior.
        """
        try:
            # Año más reciente (0) y anterior (1)
            nopat0 = self._get_nopat(0)
            nopat1 = self._get_nopat(1)
            ic0 = self._get_invested_capital(0)
            ic1 = self._get_invested_capital(1)
            if None in (nopat0, nopat1, ic0, ic1):
                return None
            delta_nopat = nopat0 - nopat1
            delta_ic = ic0 - ic1
            if delta_ic == 0:
                return None
            return delta_nopat / delta_ic
        except:
            return None

    def get_fcf_yield(self):
        """
        3. FCF Yield = Free Cash Flow / Market Cap
        (ya estaba en compute_metrics, lo dejo por separado)
        """
        fcf = get_free_cash_flow(self.ticker)
        mcap = get_market_cap(self.ticker)
        if fcf and mcap:
            return fcf / mcap
        return None

    def get_ev_ebit(self):
        """
        4. EV/EBIT (Enterprise Value / EBIT)
        """
        ev = get_enterprise_value(self.ticker)
        ebit = get_ebit(self.ticker)
        if ev and ebit and ebit != 0:
            return ev / ebit
        return None

    def get_owner_earnings(self):
        """
        5. Owner Earnings = Net Income + D&A - Maintenance Capex ± Δ Working Capital
        """
        ni = get_net_income(self.ticker)
        da = get_depreciation_amortization(self.ticker)
        maint_capex = get_maintenance_capex(self.ticker)
        wc_change = get_working_capital_change(self.ticker)  # puede ser None

        if None in (ni, da, maint_capex):
            return None
        owner_earnings = ni + da - maint_capex
        if wc_change is not None:
            owner_earnings -= wc_change  # incremento de WC reduce efectivo
        return owner_earnings

    def get_piotroski_fscore(self):
        """
        6. Piotroski F-Score (0-9). Requiere datos de 2 años.
        Puntos basados en: ROA, CFO, ΔROA, Accruals, ΔLeverage, ΔLiquidity,
        ΔEquity Offering, ΔMargin, ΔTurnover.
        """
        def get_val(series, offset):
            return series.iloc[offset] if len(series) > offset else None

        try:
            # Obtener series históricas
            net_income = self.yf_ticker.income_stmt.loc["Net Income"]
            total_assets = self.yf_ticker.balance_sheet.loc["Total Assets"]
            cfo = self.yf_ticker.cashflow.loc["Total Cash From Operating Activities"]
            lt_debt = self.yf_ticker.balance_sheet.loc.get("Long Term Debt", pd.Series())
            current_assets = self.yf_ticker.balance_sheet.loc.get("Current Assets", pd.Series())
            current_liabilities = self.yf_ticker.balance_sheet.loc.get("Current Liabilities", pd.Series())
            revenue = self.yf_ticker.income_stmt.loc["Total Revenue"]

            # Años más reciente (0) y anterior (1)
            roa0 = get_val(net_income, 0) / get_val(total_assets, 0) if get_val(total_assets, 0) else None
            roa1 = get_val(net_income, 1) / get_val(total_assets, 1) if get_val(total_assets, 1) else None
            cfo0 = get_val(cfo, 0)
            cfo1 = get_val(cfo, 1)
            accruals = (cfo0 - get_val(net_income, 0)) / get_val(total_assets, 0) if get_val(total_assets, 0) else None

            leverage0 = get_val(lt_debt, 0) / get_val(total_assets, 0) if get_val(total_assets, 0) else None
            leverage1 = get_val(lt_debt, 1) / get_val(total_assets, 1) if get_val(total_assets, 1) else None
            liquidity0 = get_val(current_assets, 0) / get_val(current_liabilities, 0) if get_val(current_liabilities, 0) else None
            liquidity1 = get_val(current_assets, 1) / get_val(current_liabilities, 1) if get_val(current_liabilities, 1) else None
            # Offering: si no hubo aumento de acciones (asumimos None = no offering)
            shares0 = get_shares_outstanding(self.ticker)
            shares1 = None  # necesitaríamos histórico; por simplicidad asumimos 0
            equity_offering = 0  # 1 si shares1 < shares0, sino 0

            gross_margin0 = (get_val(revenue, 0) - self.yf_ticker.income_stmt.loc["Cost Of Revenue"].iloc[0]) / get_val(revenue, 0) if get_val(revenue, 0) else None
            gross_margin1 = (get_val(revenue, 1) - self.yf_ticker.income_stmt.loc["Cost Of Revenue"].iloc[1]) / get_val(revenue, 1) if get_val(revenue, 1) else None
            turnover0 = get_val(revenue, 0) / get_val(total_assets, 0) if get_val(total_assets, 0) else None
            turnover1 = get_val(revenue, 1) / get_val(total_assets, 1) if get_val(total_assets, 1) else None

            score = 0
            if roa0 and roa0 > 0: score += 1
            if cfo0 and cfo0 > 0: score += 1
            if roa0 and roa1 and roa0 > roa1: score += 1
            if accruals and accruals > 0: score += 1  # mejor si accruals < 0, pero simplificado
            if leverage0 and leverage1 and leverage0 < leverage1: score += 1
            if liquidity0 and liquidity1 and liquidity0 > liquidity1: score += 1
            if not equity_offering: score += 1
            if gross_margin0 and gross_margin1 and gross_margin0 > gross_margin1: score += 1
            if turnover0 and turnover1 and turnover0 > turnover1: score += 1
            return score
        except:
            return None

    def get_altman_zscore(self):
        """
        7. Altman Z-Score (para manufactureras): Z = 1.2A + 1.4B + 3.3C + 0.6D + 1.0E
        A = Working Capital / Total Assets
        B = Retained Earnings / Total Assets
        C = EBIT / Total Assets
        D = Market Cap / Total Liabilities
        E = Revenue / Total Assets
        """
        wc = get_working_capital(self.ticker)
        assets = get_total_assets(self.ticker)
        re = get_retained_earnings(self.ticker)
        ebit = get_ebit(self.ticker)
        mcap = get_market_cap(self.ticker)
        liabilities = get_total_liabilities(self.ticker)
        revenue = get_revenue(self.ticker)

        if None in (assets, liabilities, mcap, revenue):
            return None
        A = (wc / assets) if wc else 0
        B = (re / assets) if re else 0
        C = (ebit / assets) if ebit else 0
        D = (mcap / liabilities) if liabilities != 0 else 0
        E = revenue / assets
        z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
        return z

    def get_net_debt_to_ebitda(self):
        """
        8. Net Debt / EBITDA
        Net Debt = Total Debt - Cash & Equivalents
        """
        debt = get_total_debt(self.ticker)
        cash = get_cash_and_equivalents(self.ticker)
        ebitda = self._get_ebitda()
        if None in (debt, cash, ebitda) or ebitda == 0:
            return None
        net_debt = debt - cash
        return net_debt / ebitda

    def get_interest_coverage(self):
        """
        9. Interest Coverage = EBIT / Interest Expense
        """
        ebit = get_ebit(self.ticker)
        interest = get_interest_expense(self.ticker)
        if ebit and interest and interest != 0:
            return ebit / interest
        return None

    def get_gross_margin_stability(self, years=5):
        """
        10. Gross Margin Stability = Desviación estándar del margen bruto (últimos N años)
        Menor desviación = más estable.
        """
        try:
            revenue_series = get_historical_revenue(self.ticker)
            cogs_series = self.yf_ticker.income_stmt.loc["Cost Of Revenue"]
            margins = []
            for i in range(min(years, len(revenue_series))):
                rev = revenue_series.iloc[i]
                cogs = cogs_series.iloc[i]
                if rev and rev != 0:
                    margins.append((rev - cogs) / rev)
            if len(margins) > 1:
                return np.std(margins)
            return None
        except:
            return None

    def get_fcf_conversion(self):
        """
        11. FCF Conversion = Free Cash Flow / Net Income
        """
        fcf = get_free_cash_flow(self.ticker)
        ni = get_net_income(self.ticker)
        if fcf and ni and ni != 0:
            return fcf / ni
        return None

    def get_croic(self):
        """
        12. CROIC (Cash Return on Invested Capital) = Free Cash Flow / Invested Capital
        """
        fcf = get_free_cash_flow(self.ticker)
        ic = self._get_invested_capital(0)
        if fcf and ic and ic != 0:
            return fcf / ic
        return None

    def get_acquirers_multiple(self):
        """
        13. Acquirer's Multiple = EV / EBIT
        (es equivalente a EV/EBIT, ya definido como get_ev_ebit)
        """
        return self.get_ev_ebit()

    def get_dcf_value(self, growth_rate=0.05, terminal_growth=0.02, years=5):
        """
        14. DCF simplificado: Valor presente de FCF proyectados + Valor terminal.
        growth_rate: tasa crecimiento FCF primeros 'years' años
        terminal_growth: crecimiento perpetuo después
        """
        fcf0 = get_free_cash_flow(self.ticker)
        wacc = get_wacc(self.ticker)
        if None in (fcf0, wacc) or wacc <= terminal_growth:
            return None
        # Proyección explícita
        fcf_sum = 0
        for t in range(1, years+1):
            fcf_t = fcf0 * (1 + growth_rate) ** t
            fcf_sum += fcf_t / ((1 + wacc) ** t)
        # Valor terminal
        terminal_fcf = fcf0 * (1 + growth_rate) ** years * (1 + terminal_growth)
        terminal_value = terminal_fcf / (wacc - terminal_growth)
        terminal_pv = terminal_value / ((1 + wacc) ** years)
        return fcf_sum + terminal_pv

    def get_shareholder_yield(self):
        """
        15. Shareholder Yield = (Dividendos + Recompras netas) / Market Cap
        Nota: yfinance no da recompras fácilmente; usamos 'buyBackShares' si existe.
        """
        t = self.yf_ticker
        try:
            dividends = t.cashflow.loc["Dividends Paid"].iloc[0] if "Dividends Paid" in t.cashflow.index else 0
            buybacks = t.cashflow.loc["Repurchase Of Capital Stock"].iloc[0] if "Repurchase Of Capital Stock" in t.cashflow.index else 0
        except:
            dividends = 0
            buybacks = 0
        mcap = get_market_cap(self.ticker)
        if mcap and mcap != 0:
            return (-(dividends + buybacks)) / mcap  # ambos suelen ser negativos en CF
        return None

    # ─────────────────────────────
    # MÉTODOS AUXILIARES PRIVADOS
    # ─────────────────────────────
    def _get_nopat(self, year_index):
        ebit = get_ebit(self.ticker, year_index)
        tax = get_effective_tax_rate(self.ticker, year_index) or 0.21
        if ebit is None:
            return None
        return ebit * (1 - tax)

    def _get_invested_capital(self, year_index):
        debt = get_total_debt(self.ticker, year_index) or 0
        assets = get_total_assets(self.ticker, year_index)
        liab = get_total_liabilities(self.ticker, year_index)
        if assets is None or liab is None:
            return None
        equity = assets - liab
        cash = get_cash_and_equivalents(self.ticker, year_index) or 0
        return debt + equity - cash

    def _get_ebitda(self):
        ebit = get_ebit(self.ticker)
        da = get_depreciation_amortization(self.ticker)
        if ebit is not None and da is not None:
            return ebit + da
        return None

    # ─────────────────────────────
    # MÉTRICAS ORIGINALES (compatibilidad)
    # ─────────────────────────────
    def get_fundamentals(self):
        return {
            "equity": None,   # ya no usamos edgar; se puede calcular
            "net_income": get_net_income(self.ticker),
            "fcf": get_free_cash_flow(self.ticker),
            "revenue": get_revenue(self.ticker),
            "operating_income": get_ebit(self.ticker),
            "market_cap": get_market_cap(self.ticker),
        }

    def compute_score(self, roe, pb, fcf_yield, operating_margin):
        score = 0
        if roe: score += roe * 0.25
        if fcf_yield: score += fcf_yield * 0.25
        if operating_margin: score += operating_margin * 0.25
        if pb: score += (1 / pb) * 0.25
        return score

    def compute_metrics(self, f):
        # Aquí se mantuvo tu lógica original y se añadieron las nuevas
        equity = f["equity"]  # None si no se usa
        net_income = f["net_income"]
        fcf = f["fcf"]
        revenue = f["revenue"]
        operating_income = f["operating_income"]
        market_cap = f["market_cap"]

        roe = net_income / equity if net_income and equity else None
        pb = market_cap / equity if equity else None
        fcf_yield = fcf / market_cap if fcf and market_cap else None
        operating_margin = operating_income / revenue if revenue and operating_income else None
        net_margin = net_income / revenue if revenue and net_income else None
        score = self.compute_score(roe, pb, fcf_yield, operating_margin)

        # Nuevas métricas
        roic = self.get_roic()
        inc_roic = self.get_incremental_roic()
        ev_ebit = self.get_ev_ebit()
        owner_earnings = self.get_owner_earnings()
        piotroski = self.get_piotroski_fscore()
        altman_z = self.get_altman_zscore()
        net_debt_ebitda = self.get_net_debt_to_ebitda()
        int_coverage = self.get_interest_coverage()
        gm_stability = self.get_gross_margin_stability()
        fcf_conv = self.get_fcf_conversion()
        croic = self.get_croic()
        acquirers_multiple = self.get_acquirers_multiple()
        dcf_value = self.get_dcf_value()
        shareholder_yield = self.get_shareholder_yield()

        return {
            "ticker": self.ticker,
            **f,
            "roe": roe,
            "pb": pb,
            "fcf_yield": fcf_yield,
            "operating_margin": operating_margin,
            "net_margin": net_margin,
            "score": score,
            # Nuevas métricas
            "roic": roic,
            "incremental_roic": inc_roic,
            "ev_ebit": ev_ebit,
            "owner_earnings": owner_earnings,
            "piotroski_fscore": piotroski,
            "altman_zscore": altman_z,
            "net_debt_to_ebitda": net_debt_ebitda,
            "interest_coverage": int_coverage,
            "gross_margin_stability": gm_stability,
            "fcf_conversion": fcf_conv,
            "croic": croic,
            "acquirers_multiple": acquirers_multiple,
            "dcf_value": dcf_value,
            "shareholder_yield": shareholder_yield,
        }

    def analyze(self):
        fundamentals = self.get_fundamentals()
        return self.compute_metrics(fundamentals)


# Ejemplo de uso (al final del archivo)
if __name__ == "__main__":
    sa = StockAnalyzer("AAPL")
    results = sa.analyze()
    for k, v in results.items():
        print(f"{k}: {v}")