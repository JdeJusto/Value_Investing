"""Generate the offline demo bundle in ``data/demo/`` (idempotent).

Anchored on public FY2025 10-K figures (rounded) and drifted backwards with
each company's growth rate so trends exist; the numbers are **pinned
fixtures**, not a live feed. The files are written with the project's own
repositories/models so the shapes always match what the code reads.

Usage::

    python -m scripts.build_demo_data
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO = PROJECT_ROOT / "data" / "demo"

#: FY2025 anchors (rounded public figures) + how the history drifts back.


def _profile(**kwargs) -> dict:
    """Small constructor helper for the profile table below."""
    return kwargs


PROFILES: dict[str, dict] = {
    "AAPL": _profile(
        sector="Technology",
        revenue=416.0e9,
        op_margin=0.32,
        net_margin=0.27,
        equity=57.0e9,
        debt=97.0e9,
        cash=36.0e9,
        shares=15.0e9,
        price=340.0,
        rnd=0.08,
        payout=0.0,
        growth=0.08,
        da=0.06,
        ppe=0.10,
        buyback=0.02,
    ),
    "MSFT": _profile(
        sector="Technology",
        revenue=281.0e9,
        op_margin=0.45,
        net_margin=0.36,
        equity=302.0e9,
        debt=60.0e9,
        cash=80.0e9,
        shares=7.43e9,
        price=510.0,
        rnd=0.13,
        payout=0.25,
        growth=0.12,
        da=0.05,
        ppe=0.20,
        buyback=0.01,
    ),
    "KO": _profile(
        sector="Consumer Defensive",
        revenue=47.9e9,
        op_margin=0.30,
        net_margin=0.27,
        equity=32.0e9,
        debt=44.0e9,
        cash=10.0e9,
        shares=4.31e9,
        price=70.0,
        rnd=0.0,
        payout=0.75,
        growth=0.04,
        da=0.02,
        ppe=0.12,
        buyback=0.0,
    ),
    "JNJ": _profile(
        sector="Healthcare",
        revenue=89.0e9,
        op_margin=0.26,
        net_margin=0.20,
        equity=71.0e9,
        debt=37.0e9,
        cash=24.0e9,
        shares=2.41e9,
        price=165.0,
        rnd=0.15,
        payout=0.45,
        growth=0.05,
        da=0.04,
        ppe=0.15,
        buyback=0.01,
    ),
    "JPM": _profile(
        sector="Financial Services",
        revenue=182.0e9,
        op_margin=0.35,
        net_margin=0.30,
        equity=350.0e9,
        debt=390.0e9,
        cash=250.0e9,
        shares=2.80e9,
        price=300.0,
        rnd=0.0,
        payout=0.30,
        growth=0.07,
        da=0.01,
        ppe=0.02,
        buyback=0.01,
    ),
    "XOM": _profile(
        sector="Energy",
        revenue=332.0e9,
        op_margin=0.12,
        net_margin=0.087,
        equity=260.0e9,
        debt=40.0e9,
        cash=30.0e9,
        shares=4.30e9,
        price=120.0,
        rnd=0.003,
        payout=0.55,
        growth=0.03,
        da=0.07,
        ppe=0.55,
        buyback=0.01,
    ),
    "PLD": _profile(
        sector="Real Estate",
        revenue=8.2e9,
        op_margin=0.45,
        net_margin=0.45,
        equity=40.0e9,
        debt=30.0e9,
        cash=2.0e9,
        shares=0.93e9,
        price=115.0,
        rnd=0.0,
        payout=0.80,
        growth=0.10,
        da=0.35,
        ppe=0.85,
        buyback=0.0,
    ),
    "TSLA": _profile(
        sector="Consumer Cyclical",
        revenue=98.0e9,
        op_margin=0.07,
        net_margin=0.04,
        equity=73.0e9,
        debt=13.0e9,
        cash=36.0e9,
        shares=3.50e9,
        price=420.0,
        rnd=0.04,
        payout=0.0,
        growth=0.25,
        da=0.05,
        ppe=0.35,
        buyback=0.0,
    ),
}

YEARS = list(range(2025, 2015, -1))  # 2025..2016
TAX_RATE = 0.21


def _rows_for(ticker: str, profile: dict) -> list:
    from backend.domain.value_objects.financials_normalized import (
        NormalizedFinancials,
    )

    rows = []
    for offset, year in enumerate(YEARS):
        decay = (1 + profile["growth"]) ** (-offset)
        revenue = profile["revenue"] * decay
        # Margins drift gently backwards so every company has a cycle reading.
        op_margin = profile["op_margin"] * (1 - 0.012 * offset)
        net_margin = profile["net_margin"] * (1 - 0.010 * offset)
        equity = profile["equity"] * (1.06 ** (-offset))
        debt = profile["debt"] * (1.03 ** (-offset))
        cash = profile["cash"] * (1.04 ** (-offset))
        shares = profile["shares"] * (1 + profile["buyback"]) ** (-offset)

        gross_margin = min(op_margin + 0.18, 0.95)
        cogs = revenue * (1 - gross_margin)
        gross_profit = revenue - cogs
        operating_income = revenue * op_margin
        opex = gross_profit - operating_income
        da = revenue * profile["da"]
        ebit = operating_income
        ebitda = ebit + da
        interest = debt * 0.04
        pretax = max(ebit - interest, 0.0)
        net_income = pretax * (1 - TAX_RATE)
        if net_margin > 0 and revenue > 0:
            # Keep the stated net margin authoritative (rounding realism).
            net_income = revenue * net_margin
            pretax = net_income / (1 - TAX_RATE)
        ocf = net_income * 1.3
        capex = revenue * 0.05
        current_assets = revenue * 0.35
        current_liabilities = revenue * 0.25
        total_liabilities = debt + current_liabilities + revenue * 0.40
        total_assets = equity + total_liabilities

        rows.append(
            NormalizedFinancials(
                ticker=ticker,
                fiscal_year=year,
                period="FY",
                revenue=revenue,
                cogs=cogs,
                gross_profit=gross_profit,
                operating_income=operating_income,
                ebit=ebit,
                ebitda=ebitda,
                net_income=net_income,
                net_income_convention=(
                    "available_to_common" if ticker == "JPM" else "consolidated"
                ),
                interest_expense=interest,
                tax_provision=pretax - net_income,
                pretax_income=pretax,
                operating_expense=opex,
                research_development=revenue * profile["rnd"],
                sga=opex * 0.6,
                total_assets=total_assets,
                total_liabilities=total_liabilities,
                total_debt=debt,
                long_term_debt=debt * 0.8,
                inventory=revenue * 0.08,
                cash_and_equivalents=cash,
                net_ppe=revenue * profile["ppe"],
                current_assets=current_assets,
                current_liabilities=current_liabilities,
                working_capital=current_assets - current_liabilities,
                retained_earnings=equity * 0.7,
                stockholders_equity=equity,
                operating_cash_flow=ocf,
                capital_expenditure=capex,
                free_cash_flow=ocf - capex,
                depreciation_amortization=da,
                dividends_paid=net_income * profile["payout"],
                preferred_dividends=net_income * 0.025 if ticker == "JPM" else 0.0,
                repurchase_of_stock=net_income * 0.1 * profile["buyback"] * 10,
                working_capital_change=0.0,
                shares_outstanding=shares,
                sector=profile["sector"],
            )
        )
    return rows


def _write_fundamentals() -> dict[str, float]:
    from backend.repositories.json_financial_repository import (
        JsonFinancialRepository,
    )

    directory = DEMO / "fundamentals"
    repository = JsonFinancialRepository(directory)
    prices: dict[str, float] = {}
    for ticker, profile in PROFILES.items():
        repository.upsert_many(_rows_for(ticker, profile))
        prices[ticker] = profile["price"]
    return prices


def _write_prices(prices: dict[str, float]) -> None:
    (DEMO / "prices.json").write_text(
        json.dumps(prices, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_rankings(prices: dict[str, float]) -> None:
    """Rank the 8 fixtures plus deterministic filler so percentiles mean something."""
    from backend.analytics.ratios.greenblatt import earnings_yield, return_on_capital
    from backend.repositories.json_financial_repository import (
        JsonFinancialRepository,
    )

    repository = JsonFinancialRepository(DEMO / "fundamentals")
    metrics: dict[str, dict] = {}
    for ticker, profile in PROFILES.items():
        rows = repository.get_best_available(ticker)
        latest = rows[0]
        roc = return_on_capital(latest)
        ey = earnings_yield(latest, prices[ticker] * profile["shares"])
        if roc is not None and ey is not None:
            metrics[ticker] = {"roc": roc, "ey": ey, "fiscal_year": latest.fiscal_year}

    # 25 filler companies: deterministic spread around the fixtures so the
    # eight real names get meaningful percentiles.
    for index in range(25):
        roc = 0.05 + 0.30 * ((index * 7) % 25) / 25
        ey = 0.01 + 0.12 * ((index * 11) % 25) / 25
        metrics[f"FILL{index:02d}"] = {"roc": roc, "ey": ey, "fiscal_year": 2025}

    ranked_roc = sorted(metrics, key=lambda t: metrics[t]["roc"], reverse=True)
    ranked_ey = sorted(metrics, key=lambda t: metrics[t]["ey"], reverse=True)
    rank_roc = {ticker: i + 1 for i, ticker in enumerate(ranked_roc)}
    rank_ey = {ticker: i + 1 for i, ticker in enumerate(ranked_ey)}
    total = len(metrics)
    rankings = {}
    for ticker in sorted(metrics):
        combined = rank_roc[ticker] + rank_ey[ticker]
        rankings[ticker] = {
            "rank_roc": rank_roc[ticker],
            "rank_ey": rank_ey[ticker],
            "combined_rank": combined,
            "percentile": combined / (2.0 * total),
            "roc": round(metrics[ticker]["roc"], 6),
            "earnings_yield": round(metrics[ticker]["ey"], 6),
            "fiscal_year": metrics[ticker]["fiscal_year"],
        }

    payload = {
        "date": datetime.now(UTC).date().isoformat(),
        "universe_size": total,
        "rankings": rankings,
    }
    target = DEMO / "rankings" / "greenblatt_demo.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_portfolio() -> None:
    from backend.portfolio.models import Portfolio, Position
    from backend.portfolio.portfolio_repository import JsonPortfolioRepository

    portfolio = Portfolio(
        positions=[
            Position(
                ticker="AAPL",
                quantity=10,
                avg_price=180.0,
                current_price=340.0,
                entry_date=datetime(2024, 3, 15, tzinfo=UTC),
                thesis="Quality compounder at a fair price",
                signal_at_entry="BUY",
            ),
            Position(
                ticker="KO",
                quantity=20,
                avg_price=58.0,
                current_price=70.0,
                entry_date=datetime(2024, 6, 3, tzinfo=UTC),
                thesis="Defensive dividend payer",
                signal_at_entry="WATCH",
            ),
            Position(
                ticker="JPM",
                quantity=15,
                avg_price=150.0,
                current_price=300.0,
                entry_date=datetime(2023, 11, 20, tzinfo=UTC),
                thesis="Best-in-class bank, bought below tangible book",
                signal_at_entry="BUY",
            ),
        ]
    )
    JsonPortfolioRepository(DEMO / "portfolio.json").save(portfolio)


def _write_report() -> None:
    target = DEMO / "reports" / "daily_demo.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """# Daily report — demo

> Demo fixture: preloaded data, no external services were used.

## Signals

| Ticker | Verdict | Score | Note |
| --- | --- | --- | --- |
| AAPL | HOLD | 54.6 | quality premium, Greenblatt mid-pack |
| KO | WATCH | 72.0 | slow grower, dividend payer |
| JPM | INSUFFICIENT | — | financial guard across book methodologies |
| XOM | HOLD | 51.0 | cyclical, above-trend margins |
| PLD | WATCH | 64.0 | REIT: DCF uses the REIT variant |

## Notes

- Greenblatt rankings come from `data/demo/rankings/greenblatt_demo.json`.
- Prices are the pinned demo snapshot; nothing is fetched or persisted.
""",
        encoding="utf-8",
    )


def main() -> int:
    prices = _write_fundamentals()
    _write_prices(prices)
    _write_rankings(prices)
    _write_portfolio()
    _write_report()
    total = sum(path.stat().st_size for path in DEMO.rglob("*") if path.is_file())
    print(f"demo bundle written to {DEMO} ({total / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
