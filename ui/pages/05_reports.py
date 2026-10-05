"""Reports — browse and preview the daily reports in data/reports/."""

from __future__ import annotations

import sys
import time
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from backend.services.ui_adapter import list_reports
from ui._shared import REPORTS_DIR, page_header


@st.cache_data(ttl=60)
def _load_reports(directory: str) -> list[dict]:
    return list_reports(directory)


@st.cache_data(ttl=60)
def _load_report_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def main() -> None:
    page_header("Reports", f"Browse the reports in {REPORTS_DIR}/")
    entries = _load_reports(str(REPORTS_DIR))
    if not entries:
        st.info(
            "No reports found. Run `python -m scripts.daily_workflow` to generate one."
        )
        return

    days = st.number_input(
        "Show reports from the last N days (0 = all)",
        min_value=0,
        max_value=365,
        value=0,
    )
    if days:
        cutoff = time.time() - days * 86400
        entries = [entry for entry in entries if entry["mtime"] >= cutoff]
        if not entries:
            st.warning(f"No reports in the last {days} days.")
            return

    labels = [
        f"{entry['filename']} · {entry['date']} · {entry['size'] / 1024:.0f} KB"
        for entry in entries
    ]
    choice = st.selectbox("Report", labels, index=0)
    entry = entries[labels.index(choice)]
    text = _load_report_text(entry["path"])

    st.download_button(
        "Download .md",
        data=text.encode("utf-8"),
        file_name=entry["filename"],
        mime="text/markdown",
        key="report_download",
    )
    st.markdown(text)


main()
