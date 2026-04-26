# analyzer.py

from edgar import Company
import yfinance as yf


class StockAnalyzer:
    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self.company = Company(self.ticker)
        self.financials = self.company.get_financials()
        self.market_data = yf.Ticker(self.ticker).info

    # ─────────────────────────────
    # DATA EXTRACTION
    # ─────────────────────────────
    def get_fundamentals(self):
        return {
            "equity": self.financials.get_stockholders_equity(),
            "net_income": self.financials.get_net_income(),
            "fcf": self.financials.get_free_cash_flow(),
            "revenue": self.financials.get_revenue(),
            "operating_income": self.financials.get_operating_income(),
            "market_cap": self.market_data.get("marketCap"),
        }

    # ─────────────────────────────
    # METRICS
    # ─────────────────────────────
    def compute_metrics(self, f):
        equity = f["equity"]
        net_income = f["net_income"]
        fcf = f["fcf"]
        revenue = f["revenue"]
        operating_income = f["operating_income"]
        market_cap = f["market_cap"]

        if not equity or not market_cap:
            return None

        roe = net_income / equity if net_income and equity else None
        pb = market_cap / equity if equity else None
        fcf_yield = fcf / market_cap if fcf and market_cap else None
        operating_margin = operating_income / revenue if revenue and operating_income else None
        net_margin = net_income / revenue if revenue and net_income else None

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
        }

    # ─────────────────────────────
    # SCORING ENGINE
    # ─────────────────────────────
    def compute_score(self, roe, pb, fcf_yield, operating_margin):
        score = 0

        if roe:
            score += roe * 0.25
        if fcf_yield:
            score += fcf_yield * 0.25
        if operating_margin:
            score += operating_margin * 0.25
        if pb:
            score += (1 / pb) * 0.25

        return score

    # ─────────────────────────────
    # PUBLIC METHOD
    # ─────────────────────────────
    def analyze(self):
        fundamentals = self.get_fundamentals()
        return self.compute_metrics(fundamentals)