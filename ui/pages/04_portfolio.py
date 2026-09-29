"""Portfolio — positions + actions (tab 1) and performance/risk (tab 2).

Reads and writes the portfolio JSON through the existing PortfolioService;
every action goes through the adapter's validation layer. Price refreshes are
in-memory until the user explicitly saves them.
"""

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
    PortfolioActionError,
    add_position,
    build_portfolio_view,
    exit_position,
    fmt_money_short,
    fmt_or_dash,
    remove_position,
)
from ui._shared import format_pct, metric_row, page_header
from ui.services import (
    load_fundamentals,
    load_portfolio,
    load_quote,
    load_sector_map,
)

DEFAULT_PORTFOLIO_PATH = "data/portfolio.json"
SIGNALS = ["BUY", "WATCH", "HOLD"]


def main() -> None:
    page_header(
        "Portfolio",
        "Positions, actions and risk. Prices refresh in memory; saving is explicit.",
    )
    path = os.environ.get("PORTFOLIO_PATH", DEFAULT_PORTFOLIO_PATH)
    portfolio = load_portfolio(path)
    if portfolio is None:
        st.error(f"No se pudo leer la cartera en {path}.")
        return
    _render_flash()
    tabs = st.tabs(["Positions", "Performance"])
    with tabs[0]:
        _positions_tab(portfolio, path)
    with tabs[1]:
        _performance_tab(portfolio)


def _view(portfolio):
    tickers = tuple(sorted({p.ticker for p in portfolio.positions if p.is_open}))
    sectors = load_sector_map(tickers) if tickers else {}
    return build_portfolio_view(portfolio, sectors)


def _positions_tab(portfolio, path: str) -> None:
    view = _view(portfolio)
    if view.is_empty:
        st.info("No hay posiciones todavía. Añade la primera con el formulario.")
    else:
        st.dataframe(view.positions, width="stretch", hide_index=True)
        _render_position_actions(portfolio, path)
        _render_refresh_prices(portfolio, path)
    st.subheader("Añadir posición")
    _render_add_form(portfolio, path)


def _performance_tab(portfolio) -> None:
    view = _view(portfolio)
    if view.is_empty:
        st.info("Sin posiciones: no hay rendimiento que mostrar.")
        return
    metric_row(
        [
            ("Valor de mercado", fmt_money_short(view.totals["market_value"])),
            ("Coste", fmt_money_short(view.totals["cost_basis"])),
            ("PnL total", fmt_money_short(view.totals["total_pnl"])),
            ("Retorno total", format_pct(view.totals["total_return"])),
            ("PnL no realizado", fmt_money_short(view.totals["unrealized_pnl"])),
            ("PnL realizado", fmt_money_short(view.totals["realized_pnl"])),
        ]
    )
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
    metric_row(
        [
            ("Mayor posición", format_pct(risk.get("largest_position_weight"))),
            ("Top-5", format_pct(risk.get("top_n_share"))),
            ("HHI", fmt_or_dash(risk.get("hhi"), digits=3)),
        ]
    )


def _render_refresh_prices(portfolio, path: str) -> None:
    st.subheader("Refresh prices")
    if st.button("Fetch current prices", key="pf_fetch"):
        quotes = {}
        for position in portfolio.positions:
            if not position.is_open:
                continue
            quote = load_quote(position.ticker)
            if quote.get("price"):
                quotes[position.ticker] = float(quote["price"])
        st.session_state["pf_quotes"] = quotes
    quotes = st.session_state.get("pf_quotes")
    if not quotes:
        st.caption("Precios en memoria; guardar es un paso aparte.")
        return
    rows = []
    for position in portfolio.positions:
        if not position.is_open or position.ticker not in quotes:
            continue
        new_price = quotes[position.ticker]
        delta = None
        if position.current_price:
            delta = (new_price - position.current_price) / position.current_price
        rows.append(
            {
                "Ticker": position.ticker,
                "Stored": position.current_price,
                "New": new_price,
                "Delta": delta,
            }
        )
    st.dataframe(
        [
            {
                "Ticker": row["Ticker"],
                "Stored": fmt_or_dash(row["Stored"]),
                "New": fmt_or_dash(row["New"]),
                "Delta": format_pct(row["Delta"]),
            }
            for row in rows
        ],
        width="stretch",
        hide_index=True,
    )
    if st.button("Save prices to portfolio", key="pf_save", type="primary"):
        from backend.portfolio.portfolio_repository import JsonPortfolioRepository

        repository = JsonPortfolioRepository(path)
        current = repository.load()
        for position in current.positions:
            if position.is_open and position.ticker in quotes:
                position.current_price = quotes[position.ticker]
        repository.save(current)
        st.session_state.pop("pf_quotes", None)
        _flash("Precios guardados en la cartera.")
        st.rerun()


def _portfolio_service(path: str):
    from backend.portfolio.portfolio_repository import JsonPortfolioRepository
    from backend.portfolio.portfolio_service import PortfolioService

    return PortfolioService(repository=JsonPortfolioRepository(path))


def _ticker_exists(ticker: str) -> bool:
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
        entry_date = col4.date_input("Fecha de entrada", value=datetime.now(UTC).date())
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
                        _portfolio_service(path), ticker, price, portfolio=portfolio
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


main()
