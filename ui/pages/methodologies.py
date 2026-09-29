"""`Metodologías + DCF` — the six book methodologies and the DCF side by side.

A view layer: everything it renders comes from the shared adapter
(``backend/services/ui_adapter.py``), which orchestrates the same registry and
DCF evaluator the CLI uses. Prices are fetched through PriceService and cached
in memory only — never persisted.
"""

from __future__ import annotations

import streamlit as st

from backend.services.ui_adapter import (
    fmt_money_short,
    fmt_or_dash,
    run_dcf,
    run_methodologies,
)
from ui.services import (
    get_price_service,
    load_fundamentals,
    load_historical_valuation,
    load_quote,
)

DCF_DISCLAIMER = (
    "**not-from-canon** — el DCF no es parte de ninguna metodología de libro "
    "y no compite con sus veredictos. Es una aproximación de valoración, "
    "sensible a los supuestos de WACC y crecimiento."
)

MAX_MULTI_TICKERS = 8


def render_methodologies():
    st.title("Metodologías + DCF")
    st.markdown(
        "Los **seis métodos de libro** y el **DCF** lado a lado para un ticker, "
        "con el resumen de desacuerdos y la valoración histórica."
    )

    ticker = st.text_input("Ticker", value="AAPL", max_chars=10).upper().strip()
    multi = st.text_input(
        "Varios tickers (separados por comas) — opcional",
        placeholder="AAPL, MSFT, KO, XOM",
    )

    if st.button("Comparar", type="primary"):
        names = [name.strip().upper() for name in multi.split(",") if name.strip()]
        if names:
            st.session_state.meth_tickers = names[:MAX_MULTI_TICKERS]
            st.session_state.meth_mode = "multi"
        elif ticker:
            st.session_state.meth_tickers = [ticker]
            st.session_state.meth_mode = "single"
        else:
            st.warning("Introduce un ticker.")
            return

    mode = st.session_state.get("meth_mode")
    names = st.session_state.get("meth_tickers") or []
    if not mode or not names:
        return

    if mode == "multi":
        _render_multi(names)
    else:
        _render_single(names[0])


def _render_single(ticker: str) -> None:
    rows = load_fundamentals(ticker)
    if not rows:
        st.error(f"No hay fundamentales para {ticker}.")
        return
    quote = load_quote(ticker)
    with st.spinner(f"Evaluando metodologías y DCF para {ticker}..."):
        view = run_methodologies(ticker, rows, quote["price"], quote["market_cap"])
        dcf = run_dcf(ticker, rows, get_price_service())

    _render_overview(rows, quote, view)
    st.divider()
    _render_methodology_table(view)
    _render_methodology_details(view)
    st.divider()
    _render_disagreement(view)
    st.divider()
    _render_dcf(dcf)
    st.divider()
    _render_history(ticker)


def _render_overview(rows, quote: dict, view) -> None:
    latest = rows[0]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Precio", fmt_or_dash(quote["price"]))
    col2.metric("Market Cap", fmt_money_short(quote["market_cap"]))
    col3.metric("Sector", latest.sector or "—")
    col4.metric("Categoría Lynch", view.category or "—")
    st.caption(
        f"Último ejercicio: FY{latest.fiscal_year} · {len(rows)} años de fundamentales"
    )


def _render_methodology_table(view) -> None:
    st.subheader("Metodologías")
    st.dataframe(view.table, width="stretch", hide_index=True)


def _render_methodology_details(view) -> None:
    st.subheader("Detalle por metodología")
    for detail in view.details:
        title = f"{detail['methodology']} — {detail['verdict']} ({detail['family']})"
        with st.expander(title):
            col1, col2, col3 = st.columns(3)
            col1.metric("Verdict", detail["verdict"])
            col2.metric("Score", fmt_or_dash(detail["score"]))
            col3.metric("Confidence", detail["confidence"])
            if detail.get("category"):
                st.caption(f"Categoría Lynch: {detail['category']}")

            outcomes = detail.get("rule_outcomes") or {}
            if outcomes:
                st.markdown("**Reglas**")
                st.dataframe(
                    [
                        {"Regla": rule_id, "Resultado": outcome}
                        for rule_id, outcome in outcomes.items()
                    ],
                    width="stretch",
                    hide_index=True,
                )

            metrics = {
                key: value
                for key, value in (detail.get("metrics") or {}).items()
                if key != "rule_outcomes"
            }
            if metrics:
                st.markdown("**Métricas**")
                st.dataframe(
                    [
                        {"Métrica": key, "Valor": _metric_value(value)}
                        for key, value in metrics.items()
                    ],
                    width="stretch",
                    hide_index=True,
                )

            reasons = detail.get("reasons") or []
            if reasons:
                st.markdown("**Reasons**")
                for reason in reasons:
                    st.markdown(f"- {reason}")

            flags = detail.get("red_flags") or []
            if flags:
                st.markdown("**Red flags**")
                for flag in flags:
                    st.markdown(f"- {flag}")


def _metric_value(value):
    """Metrics table cells are strings so Arrow never has to guess types."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "—" if value is None else str(value)
    return fmt_or_dash(value)


def _render_disagreement(view) -> None:
    st.subheader("Resumen de desacuerdos")
    if view.agreement:
        st.info("Todas las metodologías registradas coinciden en esta empresa.")
        return
    for line in view.family_lines:
        st.markdown(f"- {line}")
    if view.explanation:
        st.caption(view.explanation)
    st.markdown("**Razones por metodología**")
    for line in view.reason_lines:
        st.markdown(f"- {line}")


def _render_dcf(dcf) -> None:
    st.subheader("DCF (valoración intrínseca)")
    st.warning(DCF_DISCLAIMER)
    st.caption(f"Variante: **{dcf.variant_label}**")

    if dcf.is_insufficient:
        st.metric("Verdict", "INSUFFICIENT_DATA")
        for reason in dcf.reasons:
            st.markdown(f"- {reason}")
        if dcf.missing_inputs:
            st.caption("Faltan: " + ", ".join(dcf.missing_inputs))
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Valor intrínseco", fmt_or_dash(dcf.intrinsic_value_per_share))
    col2.metric("Precio actual", fmt_or_dash(dcf.current_price))
    col3.metric("Margen de seguridad", fmt_or_dash(dcf.margin_of_safety, percent=True))
    col4.metric("Verdict", dcf.verdict)

    with st.expander("Supuestos"):
        st.markdown(
            f"- {dcf.discount_label}: {fmt_or_dash(dcf.discount_rate, percent=True)}"
        )
        st.markdown(f"- {dcf.base_text}: {fmt_or_dash(dcf.base_value)}")
        st.markdown(
            f"- Crecimiento años 1-5: {fmt_or_dash(dcf.growth_1_5, percent=True)}"
        )
        st.markdown(
            f"- Crecimiento años 6-10: {fmt_or_dash(dcf.growth_6_10, percent=True)}"
        )
        st.markdown(
            f"- Crecimiento terminal: {fmt_or_dash(dcf.terminal_growth, percent=True)}"
        )

    if dcf.sensitivity_rows:
        st.markdown("**Sensibilidad (valor intrínseco por acción)**")
        st.dataframe(dcf.sensitivity_rows, width="stretch", hide_index=True)

    with st.expander("Notas"):
        for reason in dcf.reasons:
            st.markdown(f"- {reason}")


def _render_history(ticker: str) -> None:
    st.subheader("Valoración histórica")
    data = load_historical_valuation(ticker)
    if not data:
        st.info("Sin datos históricos de valoración para este ticker.")
        return
    pe_rows = [
        {"Ejercicio": row["fiscal_year"], "P/E": row["pe_ratio"]}
        for row in sorted(data, key=lambda r: r["fiscal_year"])
        if row.get("pe_ratio") is not None
    ]
    fcf_rows = [
        {
            "Ejercicio": row["fiscal_year"],
            "FCF Yield %": (row["fcf_yield"] or 0.0) * 100.0,
        }
        for row in sorted(data, key=lambda r: r["fiscal_year"])
        if row.get("fcf_yield") is not None
    ]
    if not pe_rows and not fcf_rows:
        st.info("Sin precios históricos suficientes para el gráfico.")
        return
    col1, col2 = st.columns(2)
    with col1:
        if pe_rows:
            st.caption("P/E por ejercicio")
            st.line_chart(pe_rows, x="Ejercicio", y="P/E")
    with col2:
        if fcf_rows:
            st.caption("FCF Yield por ejercicio (%)")
            st.line_chart(fcf_rows, x="Ejercicio", y="FCF Yield %")


def _render_multi(names: list[str]) -> None:
    st.subheader("Comparativa multi-ticker")
    for name in names:
        rows = load_fundamentals(name)
        if not rows:
            st.warning(f"{name}: sin fundamentales.")
            continue
        quote = load_quote(name)
        view = run_methodologies(name, rows, quote["price"], quote["market_cap"])
        st.markdown(f"**{name}** — Categoría Lynch: {view.category or '—'}")
        st.dataframe(view.table, width="stretch", hide_index=True)
