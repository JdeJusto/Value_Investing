"""Home — daily snapshot: portfolio, top opportunities, recent alerts."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from backend.services.ui_adapter import (
    build_portfolio_view,
    latest_daily_report,
    refresh_portfolio_prices,
    save_portfolio_prices,
)
from ui._shared import (
    DASH,
    REPORTS_DIR,
    dataframe_with_download,
    format_pct,
    metric_row,
    page_header,
    page_link,
)
from ui.services import get_price_service, load_portfolio, load_sector_map

PORTFOLIO_PATH = "data/portfolio.json"


def main() -> None:
    page_header(
        "Value Investing — Home",
        f"Daily snapshot · {datetime.now(UTC).date().isoformat()}",
    )
    _portfolio_summary()
    _latest_report()
    _quick_actions()


def _portfolio_summary() -> None:
    st.subheader("Portfolio")
    path = os.environ.get("PORTFOLIO_PATH", PORTFOLIO_PATH)
    portfolio = load_portfolio(path)
    if portfolio is None:
        st.error(f"No se pudo leer la cartera en {path}.")
        return
    tickers = tuple(sorted({p.ticker for p in portfolio.positions if p.is_open}))
    sectors = load_sector_map(tickers) if tickers else {}
    view = build_portfolio_view(portfolio, sectors)
    if view.is_empty:
        st.info("No positions yet — add one in Portfolio.")
        return
    metric_row(
        [
            ("Market value", f"${view.totals['market_value']:,.0f}"),
            ("Cost basis", f"${view.totals['cost_basis']:,.0f}"),
            ("Total PnL", f"${view.totals['total_pnl']:,.0f}"),
            ("Total return", format_pct(view.totals["total_return"])),
        ]
    )
    page_link("pages/04_portfolio.py", label="Open Portfolio")
    _refresh_prices(portfolio, path)


def _refresh_prices(portfolio, path: str) -> None:
    col1, col2 = st.columns(2)
    if col1.button("Refresh prices", key="home_refresh"):
        st.session_state["home_prices"] = refresh_portfolio_prices(
            portfolio, get_price_service()
        )
    prices = st.session_state.get("home_prices")
    if col2.button(
        "Save prices to portfolio",
        key="home_save",
        type="primary",
        disabled=not prices,
    ):
        from backend.portfolio.portfolio_repository import JsonPortfolioRepository

        updated = save_portfolio_prices(
            portfolio, prices, JsonPortfolioRepository(path)
        )
        st.session_state.pop("home_prices", None)
        st.success(f"Precios guardados en la cartera ({updated} posiciones).")
        st.rerun()
    if not prices:
        return
    st.dataframe(
        [
            {
                "Ticker": ticker,
                "Stored": f"{data['stored']:,.2f}",
                "New": f"{data['new']:,.2f}",
                "Delta": format_pct(data["delta_pct"]),
            }
            for ticker, data in prices.items()
        ],
        width="stretch",
        hide_index=True,
    )


def _latest_report() -> None:
    report = latest_daily_report(REPORTS_DIR)

    st.subheader("Top opportunities")
    if report is None:
        st.info(
            "No daily report available — run `python -m scripts.daily_workflow` first."
        )
    else:
        st.caption(
            f"Latest report: {report['filename']} · {report.get('date') or DASH}"
        )
        opportunities = [
            {
                "Ticker": row.get("Ticker"),
                "Rating": row.get("Rating"),
                "Score": row.get("Score"),
                "Rank": row.get("Rank"),
                "Signal": row.get("Signal"),
            }
            for row in report["screened"][:10]
        ]
        dataframe_with_download(
            opportunities, "top_opportunities.csv", "home_opportunities"
        )

    st.subheader("Recent alerts")
    if report is None or not report["alerts"]:
        st.info("No alerts in the latest report.")
    else:
        alerts = [
            {
                "Ticker": alert["ticker"],
                "Type": alert["kind"],
                "Severity": alert["severity"],
                "Message": alert["message"],
            }
            for alert in report["alerts"][:10]
        ]
        dataframe_with_download(alerts, "recent_alerts.csv", "home_alerts")


def _quick_actions() -> None:
    st.subheader("Quick actions")
    col1, col2, col3 = st.columns(3)
    with col1:
        page_link("pages/02_analysis.py", label="Analyze a ticker")
    with col2:
        page_link("pages/03_screener.py", label="Run screener")
    with col3:
        st.caption(
            "The full daily pipeline (SEC refresh + screening + alerts) runs "
            "from the CLI: `python -m scripts.daily_workflow`."
        )


main()
