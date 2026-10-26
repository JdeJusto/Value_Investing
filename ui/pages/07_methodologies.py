"""Methodologies page: rank by single methodology or combine several."""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from backend.methodologies.registry import discover, registry
from backend.services.methodology_ranking_service import (
    rank_by_methodology,
    rank_combined,
)
from ui._shared import dataframe_with_download, page_header
from ui.theme import inject_theme

inject_theme()
page_header("Methodologies", "Rank by methodology · Combine several")

discover()


def _get_demo_tickers() -> list[str]:
    """Get demo tickers from available data."""
    try:
        from backend.services.demo_mode import DEMO_ROOT

        demo_dir = DEMO_ROOT / "fundamentals"
        if demo_dir.exists():
            tickers = sorted([p.stem for p in demo_dir.glob("*.json")])
            return tickers
    except (OSError, ImportError):
        pass
    return []


def _get_universe_options() -> dict[str, list[str]]:
    options = {}
    demo_tickers = _get_demo_tickers()
    if demo_tickers:
        options[f"Demo ({len(demo_tickers)})"] = demo_tickers
    try:
        from ui.pages._universe import load_universe_tickers

        # Try to load some common universes
        for universe_name in ["SP500", "NASDAQ100"]:
            try:
                tickers = load_universe_tickers([universe_name])
                if tickers:
                    options[f"{universe_name} ({len(tickers)})"] = tickers
            except Exception:
                continue
    except Exception:
        pass
    if not options:
        options["Demo (0)"] = []
    return options


UNIVERSE_OPTIONS = _get_universe_options()
METHODOLOGY_NAMES = registry.list()

tab_single, tab_combine = st.tabs(["By methodology", "Combine"])

# --- Tab 1: By methodology ---
with tab_single:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        methodology = st.selectbox(
            "Methodology", METHODOLOGY_NAMES, key="single_methodology"
        )
    with col2:
        universe_label = st.selectbox(
            "Universe", list(UNIVERSE_OPTIONS.keys()), key="single_universe"
        )
    with col3:
        top_n = st.number_input(
            "Top N", min_value=5, max_value=100, value=20, step=5, key="single_topn"
        )
    with col4:
        include_na = st.checkbox("Include N/A", value=False, key="single_include_na")

    universe_tickers = UNIVERSE_OPTIONS.get(universe_label, [])

    @st.cache_data(ttl=3600, show_spinner="Ranking by methodology...")
    def _rank_single_cached(
        method_name: str, universe_key: str, n: int, include_na_flag: bool
    ):
        tickers = UNIVERSE_OPTIONS.get(universe_key, [])
        return rank_by_methodology(
            method_name, tickers, top_n=n, include_na=include_na_flag
        )

    if not universe_tickers:
        st.warning("Selected universe is empty.")
    else:
        try:
            results = _rank_single_cached(
                methodology, universe_label, int(top_n), include_na
            )
            if not results:
                st.info(
                    "No results to display (all tickers may be N/A or insufficient data)."
                )
            else:
                na_count = (
                    sum(1 for r in results if r.n_a_reason is not None)
                    if include_na
                    else 0
                )
                st.caption(f"Showing top {len(results)} by {methodology}.")
                if not include_na:
                    st.caption(
                        "N/A and INSUFFICIENT_DATA tickers are excluded by default."
                    )
                elif na_count > 0:
                    st.caption(f"{na_count} tickers shown as N/A.")

                rows = []
                for idx, r in enumerate(results, 1):
                    score_str = f"{r.score:.2f}" if r.score is not None else "—"
                    rows.append(
                        {
                            "Rank": idx,
                            "Ticker": r.ticker,
                            "Family": r.family,
                            "Verdict": r.verdict.value,
                            "Score": score_str,
                            "Action": f"[View →](./Analysis?ticker={r.ticker})",
                        }
                    )
                df = dataframe_with_download(
                    rows,
                    f"methodology_ranking_{methodology}_{universe_label.replace(' ', '_')}.csv",
                    f"methodology_ranking_{methodology}",
                )
                st.dataframe(df, hide_index=True, width="stretch")
        except (ValueError, KeyError) as e:
            st.error(f"Error ranking: {e}")

# --- Tab 2: Combine ---
with tab_combine:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        selected_methods = st.multiselect(
            "Methodologies",
            METHODOLOGY_NAMES,
            default=METHODOLOGY_NAMES[:2]
            if len(METHODOLOGY_NAMES) >= 2
            else METHODOLOGY_NAMES,
            key="combine_methods",
        )
    with col2:
        strategy = st.radio(
            "Strategy",
            ["AND", "OR", "Weighted"],
            horizontal=True,
            key="combine_strategy",
        )
    with col3:
        universe_label2 = st.selectbox(
            "Universe", list(UNIVERSE_OPTIONS.keys()), key="combine_universe"
        )
    with col4:
        top_n2 = st.number_input(
            "Top N", min_value=5, max_value=100, value=20, step=5, key="combine_topn"
        )

    universe_tickers2 = UNIVERSE_OPTIONS.get(universe_label2, [])

    @st.cache_data(ttl=3600, show_spinner="Combining methodologies...")
    def _rank_combined_cached(
        methods_tuple: tuple, universe_key: str, strategy_name: str, n: int
    ):
        tickers = UNIVERSE_OPTIONS.get(universe_key, [])
        return rank_combined(
            list(methods_tuple), tickers, strategy_name.lower(), top_n=n
        )

    if not selected_methods:
        st.warning("Select at least one methodology.")
    elif not universe_tickers2:
        st.warning("Selected universe is empty.")
    else:
        try:
            results = _rank_combined_cached(
                tuple(selected_methods), universe_label2, strategy, int(top_n2)
            )
            if not results:
                st.info("No tickers pass the combination criteria.")
            else:
                if strategy == "AND":
                    st.caption(
                        f"{len(results)} tickers pass all selected methodologies (BUY or WATCH in all)."
                    )
                elif strategy == "OR":
                    st.caption(
                        f"{len(results)} tickers pass at least one selected methodology (BUY or WATCH in any)."
                    )
                else:
                    st.caption(
                        f"{len(results)} tickers with numeric scores in all methodologies (weighted)."
                    )

                rows = []
                for idx, r in enumerate(results, 1):
                    row = {"Rank": idx, "Ticker": r.ticker}
                    for m in selected_methods:
                        rt = r.per_methodology.get(m)
                        if rt:
                            score_str = (
                                f"{rt.score:.2f}" if rt.score is not None else "—"
                            )
                            row[m] = f"{rt.verdict.value} {score_str}"
                        else:
                            row[m] = "—"
                    combined_score_str = (
                        f"{r.combined_score:.2f}"
                        if r.combined_score is not None
                        else "—"
                    )
                    row["Combined"] = combined_score_str
                    row["Combined Verdict"] = r.combined_verdict.value
                    row["Note"] = r.rationale
                    row["Action"] = f"[View →](./Analysis?ticker={r.ticker})"
                    rows.append(row)

                df = dataframe_with_download(
                    rows,
                    f"methodology_combined_{strategy}_{universe_label2.replace(' ', '_')}.csv",
                    f"methodology_combined_{strategy}",
                )
                st.dataframe(df, hide_index=True, width="stretch")
        except (ValueError, KeyError) as e:
            st.error(f"Error combining: {e}")
