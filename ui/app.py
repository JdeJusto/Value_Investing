import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

st.set_page_config(
    page_title="Value Investing",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.pages.screener import render_screener
from ui.pages.analysis import render_analysis
from ui.pages.company import render_company

PAGE_RENDERERS = {
    "Screener": render_screener,
    "Análisis Detallado": render_analysis,
    "Vista Rápida": render_company,
}


def main():
    if "page" not in st.session_state:
        st.session_state.page = "Screener"

    with st.sidebar:
        st.title("📈 Value Investing")
        st.markdown("---")
        selected = st.radio(
            "Navegación",
            options=list(PAGE_RENDERERS.keys()),
            index=list(PAGE_RENDERERS.keys()).index(st.session_state.page),
            key="nav",
        )
        if selected != st.session_state.page:
            st.session_state.page = selected
            st.rerun()

        st.markdown("---")
        st.caption("Análisis fundamental de acciones")
        st.caption("Datos: Yahoo Finance + SEC EDGAR")

    render = PAGE_RENDERERS[st.session_state.page]
    render()


if __name__ == "__main__":
    main()
