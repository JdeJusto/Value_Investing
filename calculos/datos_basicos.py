# calculos/datos_basicos.py
import yfinance as yf
import pandas as pd
import numpy as np

_ticker_cache = {}

def get_ticker(ticker):
    if ticker not in _ticker_cache:
        _ticker_cache[ticker] = yf.Ticker(ticker)
    return _ticker_cache[ticker]

def ensure_ticker(ticker_or_obj):
    if isinstance(ticker_or_obj, str):
        return get_ticker(ticker_or_obj)
    return ticker_or_obj

# ---------- Income Statement ----------
def get_revenue(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.income_stmt.loc["Total Revenue"].iloc[year_index]
    except:
        return None

def get_cogs(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.income_stmt.loc["Cost Of Revenue"].iloc[year_index]
    except:
        return None

def get_ebit(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.income_stmt.loc["Operating Income"].iloc[year_index]
    except:
        return None

def get_ebitda(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.income_stmt.loc["EBITDA"].iloc[year_index]
    except:
        ebit = get_ebit(ticker, year_index)
        da = get_depreciation_amortization(ticker, year_index)
        if ebit is not None and da is not None:
            return ebit + da
        return None

def get_net_income(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.income_stmt.loc["Net Income"].iloc[year_index]
    except:
        return None

def get_interest_expense(ticker, year_index=0):
    """Prueba varios nombres para gastos financieros"""
    t = ensure_ticker(ticker)
    candidates = ["Interest Expense", "Interest Expense Non Operating", "Net Interest Income"]
    for name in candidates:
        try:
            val = t.income_stmt.loc[name].iloc[year_index]
            if val is not None:
                return val
        except:
            continue
    return None

def get_effective_tax_rate(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        tax = t.income_stmt.loc["Tax Provision"].iloc[year_index]
        pretax = t.income_stmt.loc["Pretax Income"].iloc[year_index]
        if pretax != 0:
            return tax / pretax
    except:
        pass
    return 0.21

# ---------- Cash Flow ----------
def get_cfo(ticker, year_index=0):
    t = ensure_ticker(ticker)
    for name in ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities", "Total Cash From Operating Activities"]:
        try:
            return t.cashflow.loc[name].iloc[year_index]
        except:
            continue
    return None

def get_capex_total(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return abs(t.cashflow.loc["Capital Expenditure"].iloc[year_index])
    except:
        return None

def get_free_cash_flow(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.cashflow.loc["Free Cash Flow"].iloc[year_index]
    except:
        cfo = get_cfo(ticker, year_index)
        capex = get_capex_total(ticker, year_index)
        if cfo is not None and capex is not None:
            return cfo - capex
        return None

def get_depreciation_amortization(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.cashflow.loc["Depreciation And Amortization"].iloc[year_index]
    except:
        return None

def get_maintenance_capex(ticker, year_index=0):
    return get_capex_total(ticker, year_index)

def get_working_capital_change(ticker):
    t = ensure_ticker(ticker)
    try:
        wc_series = t.balance_sheet.loc["Working Capital"]
        if len(wc_series) >= 2:
            return wc_series.iloc[0] - wc_series.iloc[1]
    except:
        pass
    return None

# ---------- Balance Sheet ----------
def get_total_assets(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.balance_sheet.loc["Total Assets"].iloc[year_index]
    except:
        return None

def get_total_liabilities(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.balance_sheet.loc["Total Liabilities Net Minority Interest"].iloc[year_index]
    except:
        return None

def get_total_debt(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.balance_sheet.loc["Total Debt"].iloc[year_index]
    except:
        return None

def get_cash_and_equivalents(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.balance_sheet.loc["Cash And Cash Equivalents"].iloc[year_index]
    except:
        return None

def get_working_capital(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.balance_sheet.loc["Working Capital"].iloc[year_index]
    except:
        return None

def get_retained_earnings(ticker, year_index=0):
    t = ensure_ticker(ticker)
    try:
        return t.balance_sheet.loc["Retained Earnings"].iloc[year_index]
    except:
        return None

def get_shares_outstanding(ticker):
    t = ensure_ticker(ticker)
    return t.info.get('sharesOutstanding')

# ---------- Market Metrics ----------
def get_market_cap(ticker):
    t = ensure_ticker(ticker)
    return t.info.get('marketCap')

def get_enterprise_value(ticker):
    t = ensure_ticker(ticker)
    return t.info.get('enterpriseValue')

def get_current_price(ticker):
    t = ensure_ticker(ticker)
    hist = t.history(period="1d")
    if not hist.empty:
        return hist['Close'].iloc[-1]
    return None

def get_beta(ticker):
    t = ensure_ticker(ticker)
    return t.info.get('beta')

def get_risk_free_rate():
    try:
        treasury = yf.Ticker("^TNX")
        return treasury.info.get('regularMarketPrice', 4.0) / 100.0
    except:
        return 0.04

def get_cost_of_equity(ticker, market_return=0.10):
    beta = get_beta(ticker) or 1.0
    rf = get_risk_free_rate()
    return rf + beta * (market_return - rf)

def get_cost_of_debt(ticker):
    interest = get_interest_expense(ticker)
    debt = get_total_debt(ticker)
    if interest is not None and debt is not None and debt != 0:
        return interest / debt
    return 0.05

def get_wacc(ticker, target_debt_ratio=None, market_return=0.10):
    """Nunca devuelve None; usa valores por defecto en caso de fallo."""
    try:
        mcap = get_market_cap(ticker)
        debt = get_total_debt(ticker)
        if mcap is None or debt is None:
            # Valores por defecto razonables
            wd = 0.5
            we = 0.5
            cost_debt = 0.05
            tax = 0.21
            cost_equity = 0.10
        else:
            if target_debt_ratio is None:
                total_cap = mcap + debt
                if total_cap == 0:
                    wd = 0.5
                else:
                    wd = debt / total_cap
                we = 1 - wd
            else:
                wd = target_debt_ratio
                we = 1 - wd
            cost_debt = get_cost_of_debt(ticker) or 0.05
            tax = get_effective_tax_rate(ticker) or 0.21
            cost_equity = get_cost_of_equity(ticker, market_return) or 0.10
        wacc = we * cost_equity + wd * cost_debt * (1 - tax)
        return wacc
    except:
        return 0.08  # WACC por defecto

def get_fcf_growth_rate(ticker, years=5):
    t = ensure_ticker(ticker)
    try:
        fcf_series = t.cashflow.loc["Free Cash Flow"]
        if len(fcf_series) >= 2:
            first = fcf_series.iloc[-1]
            last = fcf_series.iloc[0]
            if first > 0:
                return (last / first) ** (1.0/(len(fcf_series)-1)) - 1
    except:
        pass
    return None

def get_terminal_value(ticker, fcf_growth_rate_assumption=0.03, terminal_growth_rate=0.02, projection_years=5):
    fcf_now = get_free_cash_flow(ticker)
    wacc = get_wacc(ticker)
    if fcf_now is None or wacc is None or wacc <= terminal_growth_rate:
        return None
    fcf_projected = fcf_now * (1 + fcf_growth_rate_assumption) ** projection_years
    tv = fcf_projected * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
    return tv

# ---------- Historical ----------
def get_historical_revenue(ticker):
    t = ensure_ticker(ticker)
    try:
        return t.income_stmt.loc["Total Revenue"]
    except:
        return pd.Series()

def get_historical_ebit(ticker):
    t = ensure_ticker(ticker)
    try:
        return t.income_stmt.loc["Operating Income"]
    except:
        return pd.Series()