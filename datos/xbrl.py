from edgar import set_identity, Company
import yfinance as yf
import pandas as pd

set_identity("Jaime jaimedejusto@gmail.com")

tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "META"]

results = []

for t in tickers:
    try:
        company = Company(t)
        financials = company.get_financials()

        # ─────────────────────────────
        # FUNDAMENTALS (EDGAR - CLEAN API)
        # ─────────────────────────────
        equity = financials.get_stockholders_equity()
        net_income = financials.get_net_income()
        fcf = financials.get_free_cash_flow()
        revenue = financials.get_revenue()
        operating_income = financials.get_operating_income()

        # ─────────────────────────────
        # MARKET DATA
        # ─────────────────────────────
        market_cap = yf.Ticker(t).info.get("marketCap")

        if not equity or not market_cap:
            continue

        # ─────────────────────────────
        # METRICS
        # ─────────────────────────────

        # 1. ROE
        roe = net_income / equity if equity and net_income else None

        # 2. P/B
        pb = market_cap / equity if equity else None

        # 3. FCF Yield
        fcf_yield = fcf / market_cap if fcf and market_cap else None

        # 4. Margins
        operating_margin = operating_income / revenue if revenue and operating_income else None
        net_margin = net_income / revenue if revenue and net_income else None

        # 5. Score combinado (mejor balanceado)
        score = 0

        if roe:
            score += roe * 0.25

        if fcf_yield:
            score += fcf_yield * 0.25

        if operating_margin:
            score += operating_margin * 0.25

        if pb:
            score += (1 / pb) * 0.25

        results.append({
            "ticker": t,
            "equity": equity,
            "net_income": net_income,
            "fcf": fcf,
            "market_cap": market_cap,
            "roe": roe,
            "pb": pb,
            "fcf_yield": fcf_yield,
            "operating_margin": operating_margin,
            "net_margin": net_margin,
            "score": score,
        })

    except Exception as e:
        print(f"Error {t}: {e}")


df = pd.DataFrame(results)

if not df.empty:
    df = df.sort_values("score", ascending=False)
    print(df)
else:
    print("No data extracted")