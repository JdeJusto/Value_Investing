"""Screener — filters over the master universe with an explicit Run button.

Flow (SQL-first where it is cheap):

1. Pre-filters before any screening: universe (config/universe.csv) and
   sector (one bulk query to Financial-DataBase).
2. The candidate set is capped by "Max tickers"; if verdict/category filters
   are active and the candidate set was larger, a warning says so.
3. The existing StockScreenerService screens the capped set (analytics +
   prices), then the numeric filters (market cap range, P/E, ROE, FCF yield)
   are applied.
4. Verdict and Lynch category are enriched for every screened row (the cap
   already bounds the work) and the categorical filters applied last.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from backend.services.ui_adapter import (
    apply_numeric_filters,
    enrich_rows,
    parse_universe_tickers,
    run_methodologies,
    screener_estimate,
    validate_screener_range,
)
from ui._shared import (
    UNIVERSE_PATH,
    dataframe_with_download,
    metric_row,
    page_header,
)
from ui.services import (
    get_screener_service,
    load_fundamentals,
    load_sector_map_bulk,
    load_sector_options,
)

DEFAULT_METHODOLOGY = "buffett_classic"
VERDICTS = ["BUY", "WATCH", "HOLD", "AVOID", "N/A", "INSUFFICIENT_DATA"]
CATEGORIES = [
    "SLOW_GROWER",
    "STALWART",
    "FAST_GROWER",
    "CYCLICAL",
    "TURNAROUND",
    "ASSET_PLAY",
    "UNKNOWN",
]
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
            sectors = st.multiselect("Sector", load_sector_options())
            max_tickers = st.number_input(
                "Max tickers",
                min_value=50,
                max_value=1000,
                value=300,
                step=50,
                help="Cap on the candidate set after the SQL pre-filters.",
            )
            methodology = st.selectbox(
                "Methodology",
                _methodology_names(),
                index=_default_methodology_index(),
            )
        with col2:
            mcap_min = st.number_input("Market cap min ($B)", min_value=0.0, value=0.0)
            mcap_max = st.number_input(
                "Market cap max ($B, 0 = off)", min_value=0.0, value=0.0
            )
            pe_max = st.number_input("P/E max (0 = off)", min_value=0.0, value=0.0)
        with col3:
            roe_min = st.slider("ROE min (%)", 0.0, 50.0, 0.0, 1.0)
            fcf_min = st.slider("FCF yield min (%)", 0.0, 20.0, 0.0, 0.5)
            verdicts = st.multiselect("Verdict", VERDICTS)
            categories = st.multiselect("Lynch category", CATEGORIES)
            include_funds = st.checkbox(
                "Include funds and SPACs",
                value=False,
                help=(
                    "By default, vehicles without operating revenue "
                    "(funds, trusts, ETFs, SPACs) are excluded."
                ),
            )
        estimate = screener_estimate(
            int(max_tickers), st.session_state.get("screener_speed_s")
        )
        basis = (
            "initial estimate"
            if estimate["is_initial"]
            else (f"based on {estimate['per_ticker']:.1f} s/ticker from the last run")
        )
        st.caption(
            f"Estimated runtime: {estimate['text']} for {int(max_tickers)} "
            f"tickers ({basis})."
        )
    return {
        "universes": universes,
        "sectors": sectors,
        "max_tickers": int(max_tickers),
        "methodology": methodology,
        "mcap_min": mcap_min,
        "mcap_max": mcap_max,
        "pe_max": pe_max,
        "roe_min": roe_min / 100.0,
        "fcf_min": fcf_min / 100.0,
        "verdicts": verdicts,
        "categories": categories,
        "include_funds": include_funds,
    }


def _methodology_names() -> list[str]:
    from backend.methodologies.registry import discover, registry

    discover()
    return registry.list()


def _default_methodology_index() -> int:
    names = _methodology_names()
    return names.index(DEFAULT_METHODOLOGY) if DEFAULT_METHODOLOGY in names else 0


def _run(filters: dict) -> None:
    error = validate_screener_range(filters["mcap_min"], filters["mcap_max"])
    if error:
        st.error(error)
        return
    tickers = _universe_tickers(tuple(filters["universes"]))
    if not tickers:
        st.warning("The selected universe is empty (config/universe.csv?).")
        return

    sectors: dict[str, str | None] = {}
    if filters["sectors"]:
        sectors = load_sector_map_bulk(tuple(tickers))
        tickers = [
            ticker for ticker in tickers if sectors.get(ticker) in filters["sectors"]
        ]

    candidates = len(tickers)
    if (filters["verdicts"] or filters["categories"]) and candidates > filters[
        "max_tickers"
    ]:
        st.warning(
            "The verdict/category filter applies only to the first "
            f"{filters['max_tickers']} tickers after the SQL filters "
            f"({candidates} candidates). Increase 'Max tickers' to cover more."
        )
    tickers = tickers[: filters["max_tickers"]]
    if not tickers:
        st.warning("No ticker passes the universe/sector filters.")
        return

    progress = st.progress(0.0, text=f"Screening {len(tickers)} tickers...")

    def callback(current, total, ticker):
        progress.progress(
            min(current / max(total, 1), 1.0),
            text=f"Analyzing {ticker} ({current}/{total})",
        )

    start = time.time()
    rows = _screen_cached(tuple(tickers), callback)
    progress.progress(1.0, text=f"Completed: {len(rows)} rows")
    rows = apply_numeric_filters(
        rows,
        mcap_min=filters["mcap_min"],
        mcap_max=filters["mcap_max"],
        pe_max=filters["pe_max"],
        roe_min=filters["roe_min"],
        fcf_min=filters["fcf_min"],
    )
    rows = _enrich(rows, filters["methodology"], sectors, filters["include_funds"])
    st.session_state["screener_speed_s"] = (time.time() - start) / max(len(tickers), 1)
    if filters["verdicts"]:
        rows = [row for row in rows if row["Verdict"] in filters["verdicts"]]
    if filters["categories"]:
        rows = [row for row in rows if row["Category"] in filters["categories"]]
    st.session_state["sc_rows"] = rows
    st.session_state["sc_meta"] = {
        "candidates": candidates,
        "screened": len(tickers),
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


def _enrich(
    rows: list[dict], methodology: str, sectors: dict, include_funds: bool = False
) -> list[dict]:
    tickers = [row["ticker"] for row in rows]
    if not sectors:
        sectors = load_sector_map_bulk(tuple(tickers)) if tickers else {}
    return enrich_rows(
        rows,
        methodology,
        sectors,
        load_fundamentals,
        run_methodologies,
        include_funds=include_funds,
    )


def _results() -> None:
    rows = st.session_state["sc_rows"]
    meta = st.session_state.get("sc_meta", {})
    st.caption(
        f"Candidates after SQL filters: {meta.get('candidates')} · "
        f"screened: {meta.get('screened')} · methodology: "
        f"{meta.get('methodology')} · rows: {len(rows)}"
    )
    if not rows:
        st.warning("No results with the current filters.")
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
        st.caption(f"Showing the first {DISPLAY_CAP} rows of {len(rows)}.")
    dataframe_with_download(display, "screener_results.csv", "screener_results")


main()
