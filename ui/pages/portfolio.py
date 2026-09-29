"""`Cartera` — portfolio view with validated add / exit / remove actions.

Reads and writes the portfolio JSON (``PORTFOLIO_PATH`` env or
``data/portfolio.json``) through the existing PortfolioService; every action
goes through the adapter's validation layer. Buy/sell from the CLI keeps
working unchanged.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import streamlit as st

from backend.services.ui_adapter import (
    PortfolioActionError,
    add_position,
    build_portfolio_view,
    exit_position,
    fmt_money_short,
    fmt_or_dash,
    remove_position,
)
from ui.services import (
    load_fundamentals,
    load_portfolio,
    load_quote,
    load_sector_map,
)

DEFAULT_PORTFOLIO_PATH = "data/portfolio.json"
SIGNALS = ["BUY", "WATCH", "HOLD"]


def render_portfolio():
    st.title("Cartera")
    st.markdown(
        "Posiciones, rendimiento y riesgo de concentración. Las altas, "
        "salidas y eliminaciones se validan antes de tocar el fichero."
    )

    path = os.environ.get("PORTFOLIO_PATH", DEFAULT_PORTFOLIO_PATH)
    portfolio = load_portfolio(path)
    if portfolio is None:
        st.error(f"No se pudo leer la cartera en {path}.")
        return

    _render_flash()

    tickers = tuple(sorted({p.ticker for p in portfolio.positions if p.is_open}))
    sectors = load_sector_map(tickers) if tickers else {}
    view = build_portfolio_view(portfolio, sectors)

    st.caption(f"Cartera: {view.name} · {path}")

    if view.is_empty:
        st.info("No hay posiciones todavía. Añade la primera con el formulario.")
    else:
        st.subheader("Posiciones")
        st.dataframe(view.positions, width="stretch", hide_index=True)
        _render_position_actions(portfolio, path)

    st.subheader("Añadir posición")
    _render_add_form(portfolio, path)

    if view.is_empty:
        return

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


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------
def _portfolio_service(path: str):
    from backend.portfolio.portfolio_repository import JsonPortfolioRepository
    from backend.portfolio.portfolio_service import PortfolioService

    return PortfolioService(repository=JsonPortfolioRepository(path))


def _ticker_exists(ticker: str) -> bool:
    """FDB existence check; a database failure falls back to allowing."""
    try:
        rows = load_fundamentals(ticker)
    except Exception:  # noqa: BLE001 — DB down: do not block the action
        return True
    return bool(rows)


def _flash(message: str, kind: str = "success") -> None:
    st.session_state["pf_flash"] = (kind, message)


def _render_flash() -> None:
    flash = st.session_state.pop("pf_flash", None)
    if not flash:
        return
    kind, message = flash
    if kind == "success":
        st.success(message)
    else:
        st.error(message)


def _render_add_form(portfolio, path: str) -> None:
    ticker = st.text_input("Ticker", key="pf_ticker", max_chars=10).upper().strip()

    prefill = 0.0
    if ticker:
        existing = portfolio.position(ticker)
        if existing is not None and existing.current_price:
            prefill = float(existing.current_price)
        else:
            quote = load_quote(ticker)
            if quote.get("price"):
                prefill = float(quote["price"])

    with st.form("pf_add"):
        col1, col2 = st.columns(2)
        shares = col1.number_input("Acciones", min_value=0.0, value=0.0, step=1.0)
        price = col2.number_input(
            "Precio", min_value=0.0, value=float(prefill), step=0.01
        )
        thesis = st.text_input("Tesis (opcional)")
        col3, col4 = st.columns(2)
        signal = col3.selectbox("Señal", SIGNALS)
        entry_date = col4.date_input(
            "Fecha de entrada", value=datetime.now(UTC).date()
        )
        submitted = st.form_submit_button("Añadir posición", type="primary")

    if not submitted:
        return
    try:
        add_position(
            _portfolio_service(path),
            ticker,
            shares,
            price,
            entry_date=entry_date,
            thesis=thesis,
            signal=signal,
            ticker_checker=_ticker_exists,
        )
    except PortfolioActionError as exc:
        st.error(str(exc))
    else:
        _flash(f"Posición añadida: {ticker}")
        st.rerun()


def _render_position_actions(portfolio, path: str) -> None:
    st.subheader("Acciones")
    confirm = st.session_state.get("pf_confirm")
    if confirm:
        action, ticker = confirm
        verb = "cerrar (Exit)" if action == "exit" else "eliminar (Remove)"
        st.warning(f"¿Confirmar {verb} la posición {ticker}?")
        col_yes, col_no = st.columns(2)
        if col_yes.button("Confirmar", type="primary", key="pf_yes"):
            try:
                if action == "exit":
                    position = portfolio.position(ticker)
                    quote = load_quote(ticker)
                    price = quote.get("price") or (
                        float(position.current_price) if position else 0.0
                    )
                    exit_position(
                        _portfolio_service(path),
                        ticker,
                        price,
                        portfolio=portfolio,
                    )
                    _flash(f"Posición cerrada: {ticker} (PnL realizado registrado)")
                else:
                    remove_position(
                        _portfolio_service(path), ticker, portfolio=portfolio
                    )
                    _flash(f"Posición eliminada: {ticker}")
            except PortfolioActionError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop("pf_confirm", None)
                st.rerun()
        if col_no.button("Cancelar", key="pf_no"):
            st.session_state.pop("pf_confirm", None)
            st.rerun()
        return

    for position in [p for p in portfolio.positions if p.is_open]:
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.markdown(
            f"**{position.ticker}** · {position.quantity:g} @ "
            f"${position.avg_price:,.2f}"
        )
        if col2.button("Exit", key=f"pf_exit_{position.ticker}"):
            st.session_state["pf_confirm"] = ("exit", position.ticker)
            st.rerun()
        if col3.button("Remove", key=f"pf_remove_{position.ticker}"):
            st.session_state["pf_confirm"] = ("remove", position.ticker)
            st.rerun()
