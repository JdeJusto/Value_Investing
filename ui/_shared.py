"""Shared Streamlit helpers for the Value Investing UI pages.

Kept deliberately small: formatting, headers, metric rows, dataframe +
CSV download and the cached ticker list. Every page imports from here so
the same value renders the same way everywhere.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import streamlit as st

from backend.services.demo_mode import DEMO_REPORTS, is_demo

DASH = "—"
UNIVERSE_PATH = Path("config/universe.csv")
#: Demo mode reads the pinned bundle instead of the local report archive.
REPORTS_DIR = DEMO_REPORTS if is_demo() else Path("data/reports")


def page_header(title: str, subtitle: str | None = None) -> None:
    """Consistent page header."""
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def format_value(value: Any, unit: str | None = None) -> str:
    """None -> em dash; numbers with 2 decimals; optional unit suffix."""
    if value is None:
        return DASH
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        text = f"{value:,.2f}"
        return f"{text} {unit}" if unit else text
    return str(value)


def format_pct(value: Any) -> str:
    """None -> em dash; otherwise a percentage with 2 decimals."""
    if value is None:
        return DASH
    return f"{value:.2%}"


def metric_row(items: list[tuple[str, str]]) -> None:
    """A row of st.metric widgets from (label, value) pairs."""
    columns = st.columns(max(len(items), 1))
    for column, (label, value) in zip(columns, items):
        column.metric(label, value)


def page_link(path: str, label: str) -> None:
    """st.page_link that degrades to a caption outside the navigation.

    Pages run standalone under AppTest (no st.navigation context), where
    st.page_link raises StreamlitPageNotFoundError; the caption keeps the
    reference visible instead of crashing the page.
    """
    try:
        st.page_link(path, label=label)
    except Exception:  # noqa: BLE001 — standalone runs have no navigation
        st.caption(f"{label} → {path}")


@st.cache_data(ttl=3600)
def load_ticker_list() -> list[str]:
    """Sorted tickers from the master universe file (for autocomplete)."""
    if not UNIVERSE_PATH.exists():
        return []
    with UNIVERSE_PATH.open(encoding="utf-8") as handle:
        return sorted(
            {
                row["ticker"].upper()
                for row in csv.DictReader(handle)
                if row.get("ticker")
            }
        )


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    """Serialize a list of row dicts to CSV (pure, testable)."""
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coerce mixed-type columns to strings so Arrow never has to guess.

    A column holding both numbers and strings (e.g. a metrics table with
    floats and a "HIGH" label) is stringified end to end; numeric-only
    columns keep their numbers and Nones (Arrow renders nulls). This is the
    explicit dtype normalization the UI applies before every st.dataframe.
    """
    if not rows:
        return rows
    columns = list(rows[0].keys())
    kinds: dict[str, set[str]] = {column: set() for column in columns}
    for row in rows:
        for column in columns:
            value = row.get(column)
            if value is None:
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                kinds[column].add("num")
            else:
                kinds[column].add("str")
    mixed = {column for column, seen in kinds.items() if len(seen) > 1}
    if not mixed:
        return rows
    normalized = []
    for row in rows:
        new_row = dict(row)
        for column in mixed:
            value = row.get(column)
            new_row[column] = DASH if value is None else str(value)
        normalized.append(new_row)
    return normalized


def dataframe_with_download(
    rows: list[dict[str, Any]],
    filename: str,
    key: str,
    *,
    height: int | None = None,
) -> None:
    """Sortable dataframe plus a CSV download button for the same rows."""
    if not rows:
        st.info("No rows to display.")
        return
    rows = normalize_rows(rows)
    kwargs: dict[str, Any] = {"width": "stretch", "hide_index": True}
    if height is not None:
        kwargs["height"] = height
    st.dataframe(rows, **kwargs)
    st.download_button(
        "Download CSV",
        data=rows_to_csv(rows).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        key=key,
    )
