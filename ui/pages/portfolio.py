"""`Cartera` — read-only portfolio view: positions, performance and risk.

The page reads the portfolio JSON (``PORTFOLIO_PATH`` env or
``data/portfolio.json``) and renders it through the shared adapter. It never
writes to the file: buy/sell actions stay in the CLI.
"""

from __future__ import annotations

import os

import streamlit as st

from backend.services.ui_adapter import (
    build_portfolio_view,
    fmt_money_short,
    fmt_or_dash,
)
from ui.services import load_portfolio, load_sector_map

DEFAULT_PORTFOLIO_PATH = "data/portfolio.json"


def render_portfolio():
    st.title("Cartera")
    st.markdown(
        "Vista de **solo lectura**: posiciones, rendimiento y riesgo de "
        "concentración. Las compras/ventas se hacen desde el CLI."
    )

    path = os.environ.get("PORTFOLIO_PATH", DEFAULT_PORTFOLIO_PATH)
    portfolio = load_portfolio(path)
    if portfolio is None:
        st.error(f"No se pudo leer la cartera en {path}.")
        return

    tickers = tuple(sorted({p.ticker for p in portfolio.positions if p.is_open}))
    sectors = load_sector_map(tickers) if tickers else {}
    view = build_portfolio_view(portfolio, sectors)

    st.caption(f"Cartera: {view.name} · {path}")

    if view.is_empty:
        st.info(
            "No hay posiciones todavía. Añádelas con "
            "`main.py portfolio add TICKER CANTIDAD PRECIO`."
        )
        return

    st.subheader("Posiciones")
    st.dataframe(view.positions, width="stretch", hide_index=True)

    st.subheader("Rendimiento")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Valor de mercado", fmt_money_short(view.totals["market_value"]))
    col2.metric("Coste", fmt_money_short(view.totals["cost_basis"]))
    col3.metric("PnL total", fmt_money_short(view.totals["total_pnl"]))
    col4.metric("Retorno total", fmt_or_dash(view.totals["total_return"], percent=True))
    col5, col6 = st.columns(2)
    col5.metric("PnL no realizado", fmt_money_short(view.totals["unrealized_pnl"]))
    col6.metric("PnL realizado", fmt_money_short(view.totals["realized_pnl"]))

    st.subheader("Exposición sectorial")
    if view.sector_exposure:
        st.bar_chart(
            [
                {"Sector": row["sector"], "Peso %": row["weight"] * 100.0}
                for row in view.sector_exposure
            ],
            x="Sector",
            y="Peso %",
        )
    else:
        st.info("Sin datos de sector para las posiciones.")

    st.subheader("Riesgo de concentración")
    if view.warnings:
        for warning in view.warnings:
            st.warning(warning)
    else:
        st.success("Sin sobreconcentración por posición o sector.")
    risk = view.risk
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Mayor posición",
        fmt_or_dash(risk.get("largest_position_weight"), percent=True),
    )
    col2.metric("Top-5", fmt_or_dash(risk.get("top_n_share"), percent=True))
    col3.metric("HHI", fmt_or_dash(risk.get("hhi"), digits=3))
