"""Analysis — single-ticker deep dive with tabs, plus multi-ticker compare.

Reuses the ui_adapter views (methodologies + DCF) and the existing analytics
service for the raw metrics tab. No analysis logic lives here.
"""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from backend.services.ui_adapter import (
    fmt_money_short,
    fmt_or_dash,
    run_dcf,
    run_methodologies,
)
from ui._shared import (
    dataframe_with_download,
    format_pct,
    metric_row,
    page_header,
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


def main() -> None:
    page_header(
        "Analysis",
        "Six book methodologies + DCF for one ticker; comma-separated list for a quick compare.",
    )
    ticker = st.text_input("Ticker", value="AAPL", max_chars=10, key="an_ticker")
    multi = st.text_input(
        "Multi-ticker compare (comma-separated, optional)",
        placeholder="AAPL, MSFT, KO",
        key="an_multi",
    )
    if st.button("Analyze", type="primary"):
        names = [name.strip().upper() for name in multi.split(",") if name.strip()]
        st.session_state["an_mode"] = "multi" if names else "single"
        st.session_state["an_tickers"] = (
            names[:MAX_MULTI_TICKERS] if names else [ticker.upper().strip()]
        )
    mode = st.session_state.get("an_mode")
    names = st.session_state.get("an_tickers") or []
    if not mode or not names or not names[0]:
        st.info("Enter a ticker and press Analyze.")
        return
    if mode == "multi":
        for name in names:
            _render_compact(name)
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
    tabs = st.tabs(["Overview", "Methodologies", "DCF", "Historical", "Raw"])
    with tabs[0]:
        _overview(rows, quote, view)
    with tabs[1]:
        _methodologies(view)
    with tabs[2]:
        _dcf_panel(dcf)
    with tabs[3]:
        _historical(ticker)
    with tabs[4]:
        _raw(ticker)


def _render_compact(ticker: str) -> None:
    rows = load_fundamentals(ticker)
    if not rows:
        st.warning(f"{ticker}: sin fundamentales.")
        return
    quote = load_quote(ticker)
    view = run_methodologies(ticker, rows, quote["price"], quote["market_cap"])
    st.markdown(f"**{ticker}** — Categoría Lynch: {view.category or '—'}")
    st.dataframe(view.table, width="stretch", hide_index=True)


def _overview(rows, quote: dict, view) -> None:
    latest = rows[0]
    metric_row(
        [
            ("Precio", fmt_or_dash(quote["price"])),
            ("Market Cap", fmt_money_short(quote["market_cap"])),
            ("Sector", latest.sector or "—"),
            ("Categoría Lynch", view.category or "—"),
        ]
    )
    st.caption(
        f"Último ejercicio: FY{latest.fiscal_year} · {len(rows)} años de fundamentales"
    )
    st.subheader("Resumen de desacuerdos")
    if view.agreement:
        st.info("Todas las metodologías registradas coinciden en esta empresa.")
    else:
        for line in view.family_lines:
            st.markdown(f"- {line}")
        if view.explanation:
            st.caption(view.explanation)
        for line in view.reason_lines:
            st.markdown(f"- {line}")


def _methodologies(view) -> None:
    st.dataframe(view.table, width="stretch", hide_index=True)
    for detail in view.details:
        title = f"{detail['methodology']} — {detail['verdict']} ({detail['family']})"
        with st.expander(title):
            metric_row(
                [
                    ("Verdict", detail["verdict"]),
                    ("Score", fmt_or_dash(detail["score"])),
                    ("Confidence", detail["confidence"]),
                ]
            )
            if detail.get("category"):
                st.caption(f"Categoría Lynch: {detail['category']}")
            outcomes = detail.get("rule_outcomes") or {}
            if outcomes:
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
                st.dataframe(
                    [
                        {
                            "Métrica": key,
                            "Valor": (
                                "—"
                                if value is None
                                else str(value)
                                if not isinstance(value, (int, float))
                                or isinstance(value, bool)
                                else f"{value:,.2f}"
                            ),
                        }
                        for key, value in metrics.items()
                    ],
                    width="stretch",
                    hide_index=True,
                )
            for reason in detail.get("reasons") or []:
                st.markdown(f"- {reason}")
            for flag in detail.get("red_flags") or []:
                st.markdown(f"- **{flag}**")


def _dcf_panel(dcf) -> None:
    st.warning(DCF_DISCLAIMER)
    st.caption(f"Variante: **{dcf.variant_label}**")
    if dcf.is_insufficient:
        st.metric("Verdict", "INSUFFICIENT_DATA")
        for reason in dcf.reasons:
            st.markdown(f"- {reason}")
        if dcf.missing_inputs:
            st.caption("Faltan: " + ", ".join(dcf.missing_inputs))
        return
    metric_row(
        [
            ("Valor intrínseco", fmt_or_dash(dcf.intrinsic_value_per_share)),
            ("Precio actual", fmt_or_dash(dcf.current_price)),
            ("Margen de seguridad", format_pct(dcf.margin_of_safety)),
            ("Verdict", dcf.verdict),
        ]
    )
    with st.expander("Supuestos"):
        st.markdown(
            f"- {dcf.discount_label}: {format_pct(dcf.discount_rate)}\n"
            f"- {dcf.base_text}: {fmt_or_dash(dcf.base_value)}\n"
            f"- Crecimiento años 1-5: {format_pct(dcf.growth_1_5)}\n"
            f"- Crecimiento años 6-10: {format_pct(dcf.growth_6_10)}\n"
            f"- Crecimiento terminal: {format_pct(dcf.terminal_growth)}"
        )
    if dcf.sensitivity_rows:
        st.markdown("**Sensibilidad (valor intrínseco por acción)**")
        st.dataframe(dcf.sensitivity_rows, width="stretch", hide_index=True)
    with st.expander("Notas"):
        for reason in dcf.reasons:
            st.markdown(f"- {reason}")


def _historical(ticker: str) -> None:
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


def _raw(ticker: str) -> None:
    from ui.services import get_analysis_service

    try:
        result = get_analysis_service().analyze(ticker)
    except Exception as exc:  # noqa: BLE001 — analytics failure must not crash the page
        st.error(f"El análisis de métricas falló: {exc}")
        return
    if not result:
        st.info("Sin métricas de analytics para este ticker.")
        return
    rows = [
        {
            "Métrica": key,
            "Valor": "—" if value is None else value,
        }
        for key, value in sorted(result.items())
        if not isinstance(value, (dict, list))
    ]
    dataframe_with_download(rows, f"{ticker}_metrics.csv", f"raw_{ticker}")


main()
