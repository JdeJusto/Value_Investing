import streamlit as st

from backend.analytics.interpretation import INTERPRETERS, METRICS_ORDER
from ui.components.metrics import metric_card
from ui.services import get_analysis_service, get_market_provider
from ui.utils.formatting import fmt_ratio, fmt_usd

METRIC_LABELS: dict[str, str] = {
    "roe": "ROE",
    "pb": "P/B",
    "fcf_yield": "FCF Yield",
    "operating_margin": "Operating Margin",
    "net_margin": "Net Margin",
    "roic": "ROIC",
    "incremental_roic": "Incremental ROIC",
    "ev_ebit": "EV/EBIT",
    "owner_earnings": "Owner Earnings",
    "piotroski_fscore": "Piotroski F-Score",
    "altman_zscore": "Altman Z-Score",
    "net_debt_to_ebitda": "Net Debt / EBITDA",
    "interest_coverage": "Interest Coverage",
    "gross_margin_stability": "Gross Margin Stability",
    "fcf_conversion": "FCF Conversion",
    "croic": "CROIC",
    "acquirers_multiple": "Acquirer's Multiple",
    "dcf_value": "DCF Value",
    "shareholder_yield": "Shareholder Yield",
}

METRIC_CATEGORIES: dict[str, list[str]] = {
    "Rentabilidad": ["roe", "roic", "incremental_roic", "croic"],
    "Valoración": [
        "pb",
        "per",
        "ev_ebit",
        "fcf_yield",
        "dcf_value",
        "acquirers_multiple",
    ],
    "Márgenes": [
        "operating_margin",
        "net_margin",
        "fcf_conversion",
        "gross_margin_stability",
    ],
    "Endeudamiento": ["debt_to_equity", "net_debt_to_ebitda", "interest_coverage"],
    "Calidad": [
        "piotroski_fscore",
        "altman_zscore",
        "shareholder_yield",
        "owner_earnings",
    ],
}


def render_analysis():
    st.title("Análisis Detallado")
    st.markdown("Análisis fundamental completo de una empresa con los 19+ indicadores.")

    ticker = st.text_input("Ticker", value="AAPL", max_chars=10).upper().strip()

    if st.button("Analizar", type="primary"):
        if not ticker:
            st.warning("Introduce un ticker.")
            return

        service = get_analysis_service()
        market = get_market_provider()

        with st.spinner(f"Obteniendo datos para {ticker}..."):
            result = service.analyze(ticker)

        if result is None:
            st.error(f"No se pudieron obtener datos para {ticker}.")
            return

        try:
            name = market.get_company_name(ticker)
            price = market.get_current_price(ticker)
            market_cap = market.get_market_cap(ticker)
        except Exception:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
            name = price = market_cap = None
            st.warning("No se pudo obtener la cotización actual de mercado.")

        st.session_state.analysis_result = result
        st.session_state.analysis_ticker = ticker
        st.session_state.analysis_name = name
        st.session_state.analysis_price = price
        st.session_state.analysis_market_cap = market_cap

    if st.session_state.get("analysis_result"):
        result = st.session_state.analysis_result
        ticker = st.session_state.analysis_ticker
        name = st.session_state.analysis_name
        price = st.session_state.analysis_price
        market_cap = st.session_state.analysis_market_cap

        st.divider()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Empresa", name or ticker)
        with col2:
            st.metric("Precio", fmt_usd(price) if price else "N/A")
        with col3:
            st.metric("Market Cap", fmt_usd(market_cap) if market_cap else "N/A")
        with col4:
            score = result.get("score", 0.0)
            st.metric("Score", fmt_ratio(score, 4))

        st.divider()

        for category, metric_keys in METRIC_CATEGORIES.items():
            st.subheader(category)
            cols = st.columns(min(len(metric_keys), 4))
            for col, key in zip(cols, metric_keys):
                val = result.get(key)
                if val is not None:
                    with col:
                        label = METRIC_LABELS.get(key, key)
                        interpret_fn = INTERPRETERS.get(key)
                        interpretation = (
                            interpret_fn(val)
                            if interpret_fn and val is not None
                            else ""
                        )
                        metric_card(label, val, interpretation)

        st.divider()
        st.subheader("Todas las métricas")
        for key in METRICS_ORDER:
            val = result.get(key)
            if val is not None:
                label = METRIC_LABELS.get(key, key)
                interpret_fn = INTERPRETERS.get(key)
                interpretation = (
                    interpret_fn(val) if interpret_fn and val is not None else ""
                )
                metric_card(label, val, interpretation)
