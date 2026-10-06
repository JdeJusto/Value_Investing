"""Value Investing — Streamlit entry point (5-page app).

Navigation is programmatic (``st.navigation``) so the pages carry stable
titles and the old manual radio is gone. Pages live in ``ui/pages/`` as
numbered scripts and run standalone under ``AppTest`` too.
"""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

st.set_page_config(
    page_title="Value Investing",
    layout="wide",
    initial_sidebar_state="expanded",
)

from backend.services.demo_mode import BANNER, is_demo

if is_demo():
    st.info(BANNER)

pages = [
    st.Page("pages/01_home.py", title="Home", default=True),
    st.Page("pages/02_analysis.py", title="Analysis"),
    st.Page("pages/03_screener.py", title="Screener"),
    st.Page("pages/04_portfolio.py", title="Portfolio"),
    st.Page("pages/05_reports.py", title="Reports"),
    st.Page("pages/06_consensus.py", title="Consensus"),
]

st.navigation(pages).run()
