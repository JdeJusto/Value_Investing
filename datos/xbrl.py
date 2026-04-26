from edgar import set_identity, Company
import yfinance as yf
import pandas as pd

set_identity("Jaime jaimedejusto@gmail.com")

tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "META"]

results = []

def safe(val):
    return val if val not in [None, 0] else None


for t in tickers:
    try:
        company = Company(t)
        financials = company.get_financials()

        # ─────────────────────────────
        # FUNDAMENTALS (EDGAR)
        # ─────────────────────────────
        equity = safe(financials.get_stockholders_equity())
        net_income = safe(financials.get_net_income())
        fcf = safe(financials.get_free_cash_flow())

        # ─────────────────────────────
        # MARKET DATA (YFINANCE)
        # ─────────────────────────────
        market_cap = yf.Ticker(t).info.get("marketCap")

        if not equity or not market_cap:
            continue

        # ─────────────────────────────
        # METRICS
        # ─────────────────────────────

        # 1. ROE
        roe = net_income / equity if net_income and equity else None

        # 2. P/B
        pb = market_cap / equity if equity else None

        # 3. FCF Yield
        fcf_yield = fcf / market_cap if fcf and market_cap else None

        # 4. Score combinado (simple y efectivo)
        score = 0

        if roe:
            score += roe * 0.4
        if fcf_yield:
            score += fcf_yield * 0.4
        if pb:
            score += (1 / pb) * 0.2  # inverso: más barato = mejor

        results.append({
            "ticker": t,
            "equity": equity,
            "net_income": net_income,
            "fcf": fcf,
            "market_cap": market_cap,
            "roe": roe,
            "pb": pb,
            "fcf_yield": fcf_yield,
            "score": score
        })

    except Exception as e:
        print(f"Error {t}: {e}")


df = pd.DataFrame(results)

if not df.empty:
    df = df.sort_values("score", ascending=False)
    print(df)
else:
    print("No data extracted")