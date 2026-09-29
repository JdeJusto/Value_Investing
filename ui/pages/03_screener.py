"""Screener — interactive filters over the master universe.

Nothing runs on page load: the user clicks "Run screener". The heavy lifting
is the existing StockScreenerService (analytics + prices); the methodology
verdict and Lynch category columns come from the ui_adapter evaluation of the
displayed rows only (capped), never the whole universe.
"""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from backend.services.ui_adapter import (
    apply_numeric_filters,
    parse_universe_tickers,
    run_methodologies,
)
from ui._shared import (
    UNIVERSE_PATH,
    dataframe_with_download,
    metric_row,
    page_header,
)
from ui.services import get_screener_service, load_fundamentals, load_sector_map

DEFAULT_METHODOLOGY = "buffett_classic"
VERDICTS = ["BUY", "WATCH", "HOLD", "AVOID", "INSUFFICIENT_DATA"]
CATEGORIES = [
    "SLOW_GROWER",
    "STALWART",
    "FAST_GROWER",
    "CYCLICAL",
    "TURNAROUND",
    "ASSET_PLAY",
    "UNKNOWN",
]
ENRICH_CAP = 300
DISPLAY_CAP = 200


def main() -> None:
    page_header(
        "Screener",
        "Filters over config/universe.csv. Click Run — nothing screens on page load.",
    )
    filters = _filter_panel()
    if st.button("Run screener", type="primary"):
        _run(filters)
    if st.session_state.get("sc_rows") is not None:
        _results()


def _filter_panel() -> dict:
    with st.expander("Filters", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            universes = st.multiselect(
                "Universe",
                ["SP500", "NASDAQ100", "Russell2000", "All"],
                default=["SP500"],
            )
            max_tickers = st.number_input(
                "Max tickers", min_value=50, max_value=2000, value=300, step=50
            )
            methodology = st.selectbox(
                "Methodology",
                _methodology_names(),
                index=_default_methodology_index(),
            )
        with col2:
            mcap_min = st.number_input("Market cap min ($B)", min_value=0.0, value=0.0)
            pe_max = st.number_input("P/E max (0 = off)", min_value=0.0, value=0.0)
            fcf_min = st.slider("FCF yield min (%)", 0.0, 20.0, 0.0, 0.5)
        with col3:
            roe_min = st.slider("ROE min (%)", 0.0, 50.0, 0.0, 1.0)
            verdicts = st.multiselect("Verdict", VERDICTS)
            categories = st.multiselect("Lynch category", CATEGORIES)
    return {
        "universes": universes,
        "max_tickers": int(max_tickers),
        "methodology": methodology,
        "mcap_min": mcap_min,
        "pe_max": pe_max,
        "fcf_min": fcf_min / 100.0,
        "roe_min": roe_min / 100.0,
        "verdicts": verdicts,
        "categories": categories,
    }


def _methodology_names() -> list[str]:
    from backend.methodologies.registry import discover, registry

    discover()
    return registry.list()


def _default_methodology_index() -> int:
    names = _methodology_names()
    return names.index(DEFAULT_METHODOLOGY) if DEFAULT_METHODOLOGY in names else 0


def _run(filters: dict) -> None:
    tickers = _universe_tickers(tuple(filters["universes"]))[: filters["max_tickers"]]
    if not tickers:
        st.warning("El universo seleccionado está vacío (¿config/universe.csv?).")
        return
    progress = st.progress(0.0, text=f"Screening {len(tickers)} tickers...")

    def callback(current, total, ticker):
        progress.progress(
            min(current / max(total, 1), 1.0),
            text=f"Analizando {ticker} ({current}/{total})",
        )

    rows = _screen_cached(tuple(tickers), callback)
    progress.progress(1.0, text=f"Completado: {len(rows)} filas")
    rows = _apply_numeric_filters(rows, filters)
    rows = _enrich(rows[:ENRICH_CAP], filters["methodology"])
    if filters["verdicts"]:
        rows = [row for row in rows if row["Verdict"] in filters["verdicts"]]
    if filters["categories"]:
        rows = [row for row in rows if row["Category"] in filters["categories"]]
    st.session_state["sc_rows"] = rows
    st.session_state["sc_meta"] = {
        "universe": len(tickers),
        "methodology": filters["methodology"],
    }


@st.cache_data(ttl=300, show_spinner=False)
def _screen_cached(tickers: tuple[str, ...], _callback) -> list[dict]:
    rows = get_screener_service().screen(
        tickers=list(tickers),
        filters=None,
        top_n=len(tickers),
        progress_callback=_callback,
    )
    fields = [
        "ticker",
        "name",
        "price",
        "market_cap",
        "per",
        "pb",
        "roe",
        "roic",
        "fcf_yield",
        "ev_ebit",
        "debt_to_equity",
        "operating_margin",
        "net_margin",
        "revenue_growth",
        "score",
    ]
    return [{field: getattr(row, field, None) for field in fields} for row in rows]


@st.cache_data(ttl=3600)
def _universe_tickers(universes: tuple[str, ...]) -> list[str]:
    if not UNIVERSE_PATH.exists():
        return []
    return parse_universe_tickers(UNIVERSE_PATH.read_text(encoding="utf-8"), universes)


def _apply_numeric_filters(rows: list[dict], filters: dict) -> list[dict]:
    return apply_numeric_filters(
        rows,
        mcap_min=filters["mcap_min"],
        pe_max=filters["pe_max"],
        roe_min=filters["roe_min"],
        fcf_min=filters["fcf_min"],
    )


def _enrich(rows: list[dict], methodology: str) -> list[dict]:
    tickers = [row["ticker"] for row in rows]
    sectors = load_sector_map(tuple(tickers)) if tickers else {}
    enriched = []
    for row in rows:
        ticker = row["ticker"]
        verdict = score = category = None
        fundamentals = load_fundamentals(ticker)
        if fundamentals:
            view = run_methodologies(ticker, fundamentals, row.get("price"))
            detail = next(
                (d for d in view.details if d["methodology"] == methodology), None
            )
            if detail:
                verdict = detail["verdict"]
                score = detail["score"]
            category = view.category
        enriched.append(
            {
                "Ticker": ticker,
                "Name": row.get("name"),
                "Sector": sectors.get(ticker),
                "Price": row.get("price"),
                "P/E": row.get("per"),
                "FCF Yield": row.get("fcf_yield"),
                "ROE": row.get("roe"),
                "Verdict": verdict,
                "Score": score,
                "Category": category,
            }
        )
    return enriched


def _results() -> None:
    rows = st.session_state["sc_rows"]
    meta = st.session_state.get("sc_meta", {})
    st.caption(
        f"Universo: {meta.get('universe')} tickers · metodología: "
        f"{meta.get('methodology')} · filas: {len(rows)}"
    )
    if not rows:
        st.warning("Ningún resultado con los filtros actuales.")
        return
    counts: dict[str, int] = {}
    for row in rows:
        key = row["Verdict"] or "N/A"
        counts[key] = counts.get(key, 0) + 1
    metric_row(
        [("Matched", str(len(rows)))]
        + [(verdict, str(counts.get(verdict, 0))) for verdict in VERDICTS]
    )
    display = rows[:DISPLAY_CAP]
    if len(rows) > DISPLAY_CAP:
        st.caption(f"Mostrando las primeras {DISPLAY_CAP} filas de {len(rows)}.")
    dataframe_with_download(display, "screener_results.csv", "screener_results")


main()
