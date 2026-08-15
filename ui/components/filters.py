import streamlit as st

from backend.domain.value_objects.filter_criteria import FilterCriteria

FILTER_FIELDS = {
    "PER": "per",
    "P/B": "pb",
    "ROE": "roe",
    "ROIC": "roic",
    "FCF Yield": "fcf_yield",
    "EV/EBIT": "ev_ebit",
    "D/E": "debt_to_equity",
    "Net Margin": "net_margin",
    "Op. Margin": "operating_margin",
    "Rev. Growth": "revenue_growth",
}


def render_filter_controls() -> list[FilterCriteria]:
    st.sidebar.header("Filtros")

    filters: list[FilterCriteria] = []
    enabled_filters = st.sidebar.multiselect(
        "Métricas a filtrar",
        options=list(FILTER_FIELDS.keys()),
        default=["PER", "P/B", "ROE"],
    )

    for label in enabled_filters:
        field = FILTER_FIELDS[label]
        filter_type = st.sidebar.radio(
            f"{label} — tipo",
            options=["Máximo", "Mínimo", "Rango"],
            horizontal=True,
            key=f"type_{field}",
        )

        if filter_type == "Máximo":
            val = st.sidebar.number_input(
                f"{label} máx",
                value=None,
                step=(
                    0.01
                    if field
                    in ("roe", "roic", "fcf_yield", "net_margin", "operating_margin")
                    else 1.0
                ),
                key=f"max_{field}",
            )
            if val is not None:
                if field in (
                    "roe",
                    "roic",
                    "fcf_yield",
                    "net_margin",
                    "operating_margin",
                    "revenue_growth",
                ):
                    filters.append(FilterCriteria.lt(field, val))
                else:
                    filters.append(FilterCriteria.lt(field, val))

        elif filter_type == "Mínimo":
            val = st.sidebar.number_input(
                f"{label} mín",
                value=None,
                step=(
                    0.01
                    if field
                    in ("roe", "roic", "fcf_yield", "net_margin", "operating_margin")
                    else 1.0
                ),
                key=f"min_{field}",
            )
            if val is not None:
                if field in (
                    "roe",
                    "roic",
                    "fcf_yield",
                    "net_margin",
                    "operating_margin",
                    "revenue_growth",
                ):
                    filters.append(FilterCriteria.gt(field, val))
                else:
                    filters.append(FilterCriteria.gt(field, val))

        elif filter_type == "Rango":
            col1, col2 = st.sidebar.columns(2)
            with col1:
                low = st.number_input(
                    f"{label} desde",
                    value=None,
                    step=(
                        0.01
                        if field
                        in (
                            "roe",
                            "roic",
                            "fcf_yield",
                            "net_margin",
                            "operating_margin",
                        )
                        else 1.0
                    ),
                    key=f"low_{field}",
                )
            with col2:
                high = st.number_input(
                    f"{label} hasta",
                    value=None,
                    step=(
                        0.01
                        if field
                        in (
                            "roe",
                            "roic",
                            "fcf_yield",
                            "net_margin",
                            "operating_margin",
                        )
                        else 1.0
                    ),
                    key=f"high_{field}",
                )
            if low is not None and high is not None:
                filters.append(FilterCriteria.between(field, low, high))

    return filters
