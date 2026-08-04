import pandas as pd
import streamlit as st

from backend.domain.value_objects.filter_criteria import FilterCriteria
from backend.providers.tickers import TICKERS
from ui.components.filters import render_filter_controls
from ui.services import get_screener_service
from ui.utils.formatting import fmt_pct, fmt_ratio, fmt_usd

SCREENER_COLUMNS = {
    "Ticker": "ticker",
    "Nombre": "name",
    "Precio": "price",
    "Market Cap": "market_cap",
    "PER": "per",
    "P/B": "pb",
    "ROE": "roe",
    "ROIC": "roic",
    "FCF Yield": "fcf_yield",
    "EV/EBIT": "ev_ebit",
    "D/E": "debt_to_equity",
    "Op. Margin": "operating_margin",
    "Net Margin": "net_margin",
    "Rev. Growth": "revenue_growth",
    "Score": "score",
}


def _fmt_cell(col: str, val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    if col in ("ROE", "ROIC", "FCF Yield", "Op. Margin", "Net Margin", "Rev. Growth"):
        return fmt_pct(val, 1)
    if col in ("PER", "P/B", "EV/EBIT", "D/E", "Score"):
        return fmt_ratio(val, 2)
    if col in ("Precio", "Market Cap"):
        return fmt_usd(val)
    return str(val)


def _build_df(results) -> pd.DataFrame:
    rows = []
    for r in results:
        row = {}
        for display, attr in SCREENER_COLUMNS.items():
            row[display] = getattr(r, attr, None)
        rows.append(row)
    df = pd.DataFrame(rows)
    for col in df.columns:
        df[col] = df[col].apply(lambda v, c=col: _fmt_cell(c, v))
    return df


def render_screener():
    st.title("Stock Screener")
    st.markdown("Filtra el universo de ~150 acciones por métricas fundamentales.")

    filters: list[FilterCriteria] = render_filter_controls()

    col1, col2, col3 = st.columns(3)
    with col1:
        top_n = st.number_input("Top N resultados", min_value=1, max_value=100, value=25)
    with col2:
        ticker_input = st.text_input("Tickers (separados por coma, vacío = todos)", placeholder="AAPL,MSFT,GOOGL")

    tickers = None
    if ticker_input.strip():
        tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]

    if st.button("Ejecutar Screener", type="primary", use_container_width=True):
        screener = get_screener_service()

        progress_bar = st.progress(0, text="Preparando...")
        total = len(tickers) if tickers else len(TICKERS)

        def progress_cb(current, total_stocks, ticker):
            progress_bar.progress(
                min(current / max(total_stocks, 1), 1.0),
                text=f"Analizando {ticker} ({current}/{total_stocks})",
            )

        results = screener.screen(
            tickers=tickers,
            filters=filters if filters else None,
            top_n=top_n,
            progress_callback=progress_cb,
        )

        progress_bar.progress(1.0, text=f"Completado: {len(results)} resultados")

        if results:
            st.session_state.screener_results = results
            st.session_state.screener_run = True
        else:
            st.warning("No se encontraron resultados con los filtros actuales.")
            st.session_state.screener_run = False

    if st.session_state.get("screener_run") and st.session_state.get("screener_results"):
        results = st.session_state.screener_results
        st.markdown(f"### {len(results)} resultados")

        df = _build_df(results)
        st.dataframe(df, use_container_width=True, hide_index=True)

        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Descargar CSV",
            data=csv_data,
            file_name="screener_results.csv",
            mime="text/csv",
        )
