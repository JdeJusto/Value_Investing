"""Consensus — where the eight book methodologies agree (and disagree).

Reads the precomputed consensus JSON (see ``docs/consensus_screener.md``):
top by consensus, best per Lynch category, the disagreement zone and the full
verdict matrix. Pure aggregation over a local file: no network, no LLM.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from backend.services.consensus_service import (
    LYNCH_CATEGORIES,
    CompanyConsensus,
    ConsensusService,
    default_consensus_dir,
)
from ui._shared import dataframe_with_download, page_header

_PAGE_CAPTION = (
    "Aggregates verdicts from all 8 book methodologies. The default ranking "
    "sorts by consensus score (BUYs minus AVOIDs); the disagreement zone "
    "shows where judgment matters most."
)
_MISSING = (
    "No consensus data available. Run "
    "`python -m scripts.compute_consensus_rankings --universe sp500` "
    "to generate it."
)

#: UI sort lenses. Score first: with 8 strict rules, 2-3 BUYs is common and
#: the AVOID count is what breaks the ties.
_SORT_KEYS = {
    "Consensus score": lambda company: (
        -company.consensus_score,
        -company.buy_count,
        company.avoid_count,
        company.ticker,
    ),
    "BUYs": lambda company: (
        -company.buy_count,
        -company.consensus_score,
        company.avoid_count,
        company.ticker,
    ),
    "AVOIDs": lambda company: (
        -company.avoid_count,
        -company.buy_count,
        company.ticker,
    ),
}
_TOP_N = 20


def _available_reports(directory: Path) -> list[dict]:
    """Metadata of every consensus file in the directory (newest last)."""
    reports: list[dict] = []
    for path in sorted(directory.glob("consensus_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        fallback_date = path.stem.removeprefix("consensus_")
        reports.append(
            {
                "path": path,
                "date": str(payload.get("date") or fallback_date),
                "universe": str(payload.get("universe") or "unknown"),
            }
        )
    return reports


def _compact(company: CompanyConsensus) -> str:
    """Verdicts in the file's canonical methodology order, slash-separated."""
    return "/".join(company.verdicts.values())


def _rank_rows(companies: list[CompanyConsensus]) -> list[dict]:
    return [
        {
            "Rank": rank,
            "Ticker": company.ticker,
            "Name": company.name,
            "Category": company.lynch_category,
            "BUYs": company.buy_count,
            "AVOIDs": company.avoid_count,
            "Consensus score": company.consensus_score,
            "Verdicts": _compact(company),
        }
        for rank, company in enumerate(companies, 1)
    ]


def _verdict_rows(companies: list[CompanyConsensus]) -> list[dict]:
    return [
        {"Ticker": company.ticker, "Name": company.name, **company.verdicts}
        for company in companies
    ]


def main() -> None:
    page_header("Consensus", _PAGE_CAPTION)
    directory = default_consensus_dir()
    reports = _available_reports(directory)
    if not reports:
        st.info(_MISSING)
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        universes = sorted({report["universe"] for report in reports})
        universe = st.selectbox("Universe", universes)
    universe_reports = [report for report in reports if report["universe"] == universe]
    with col2:
        dates = sorted({report["date"] for report in universe_reports}, reverse=True)
        date = st.selectbox("Date", dates)
    with col3:
        categories = st.multiselect("Lynch category", list(LYNCH_CATEGORIES))

    service = ConsensusService(directory=directory)
    selected = next(report for report in universe_reports if report["date"] == date)
    report = service.load_file(selected["path"])
    if report is None:
        st.warning(f"Consensus file for {date} could not be read.")
        return

    sort_by = st.radio(
        "Sort by",
        list(_SORT_KEYS),
        horizontal=True,
        key=f"consensus_sort_{report.date}",
    )
    top = service.top_by_consensus(10_000)
    if categories:
        top = [company for company in top if company.lynch_category in categories]
    top = sorted(top, key=_SORT_KEYS[sort_by])[:_TOP_N]
    st.subheader("Top by consensus")
    dataframe_with_download(
        _rank_rows(top),
        f"consensus_{report.date}.csv",
        f"consensus_top_{report.date}",
    )

    with st.expander("Best per Lynch category", expanded=False):
        grouped = service.best_per_lynch_category(5)
        for category in LYNCH_CATEGORIES:
            st.markdown(f"**{category}**")
            companies = grouped.get(category) or []
            if not companies:
                st.caption("No companies in this category.")
                continue
            st.dataframe(_rank_rows(companies), hide_index=True, width="stretch")

    with st.expander("Disagreement zone (3-5 BUYs and 3-5 AVOIDs)", expanded=False):
        zone = service.disagreement_zone(3, 5)
        if not zone:
            st.caption("No companies in the disagreement zone.")
        else:
            st.dataframe(_verdict_rows(zone), hide_index=True, width="stretch")

    with st.expander("Verdict matrix", expanded=False):
        st.caption(
            "One row per company, one column per methodology: BUY, WATCH, "
            "HOLD, AVOID or INSUFFICIENT_DATA."
        )
        st.dataframe(service.verdict_matrix(), hide_index=True, width="stretch")


main()
