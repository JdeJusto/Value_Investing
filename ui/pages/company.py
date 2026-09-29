import streamlit as st

from backend.analytics.interpretation import INTERPRETERS
from ui.components.metrics import metric_card
from ui.pages.analysis import METRIC_LABELS
from ui.services import get_analysis_service, get_market_provider
from ui.utils.formatting import fmt_usd

QUICK_METRICS = [
    "roe",
    "roic",
    "pb",
    "per",
    "fcf_yield",
    "ev_ebit",
    "debt_to_equity",
    "operating_margin",
    "net_margin",
    "piotroski_fscore",
    "altman_zscore",
    "dcf_value",
    "shareholder_yield",
    "score",
]


def render_company():
    st.title("Vista Rápida")
    st.markdown("Resumen ejecutivo: precio, market cap y métricas clave.")

    ticker = st.text_input("Ticker", value="AAPL", max_chars=10).upper().strip()

    if st.button("Consultar", type="primary"):
        if not ticker:
            st.warning("Introduce un ticker.")
            return

        service = get_analysis_service()
        market = get_market_provider()

        with st.spinner(f"Obteniendo datos para {ticker}..."):
            try:
                name = market.get_company_name(ticker)
                price = market.get_current_price(ticker)
                market_cap = market.get_market_cap(ticker)
            except Exception:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
                name = price = market_cap = None
                st.warning("No se pudo obtener la cotización actual de mercado.")
            result = service.analyze(ticker)

        st.session_state.company_result = result
        st.session_state.company_ticker = ticker
        st.session_state.company_name = name
        st.session_state.company_price = price
        st.session_state.company_market_cap = market_cap

    if st.session_state.get("company_result"):
        result = st.session_state.company_result
        ticker = st.session_state.company_ticker
        name = st.session_state.company_name
        price = st.session_state.company_price
        market_cap = st.session_state.company_market_cap

        if result is None:
            st.error(f"No se pudieron obtener datos para {ticker}.")
            return

        st.divider()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Empresa", name or ticker)
        with col2:
            st.metric("Precio", fmt_usd(price) if price else "N/A")
        with col3:
            st.metric("Market Cap", fmt_usd(market_cap) if market_cap else "N/A")
        with col4:
            score = result.get("score") if result else None
            st.metric("Score", f"{score:.4f}" if score is not None else "N/A")

        st.divider()

        if result:
            for i in range(0, len(QUICK_METRICS), 4):
                cols = st.columns(4)
                for col, key in zip(cols, QUICK_METRICS[i : i + 4]):
                    val = result.get(key)
                    if val is not None:
                        with col:
                            label = METRIC_LABELS.get(key, key)
                            interpret_fn = INTERPRETERS.get(key)
                            interpretation = interpret_fn(val) if interpret_fn else ""
                            metric_card(label, val, interpretation)
