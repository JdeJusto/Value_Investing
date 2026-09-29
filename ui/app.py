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

from ui.pages.analysis import render_analysis
from ui.pages.company import render_company
from ui.pages.methodologies import render_methodologies
from ui.pages.screener import render_screener

PAGE_RENDERERS = {
    "Screener": render_screener,
    "Metodologías + DCF": render_methodologies,
    "Análisis Detallado": render_analysis,
    "Vista Rápida": render_company,
}


def main():
    if "page" not in st.session_state:
        st.session_state.page = "Screener"

    with st.sidebar:
        st.title("📈 Value Investing")
        st.markdown("---")
        options = list(PAGE_RENDERERS.keys())
        page = st.session_state.page if st.session_state.page in options else options[0]
        selected = st.radio(
            "Navegación",
            options=options,
            index=options.index(page),
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
