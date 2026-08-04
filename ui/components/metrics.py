import streamlit as st
from ui.utils.formatting import fmt_usd, fmt_pct, fmt_ratio


def metric_card(label: str, value: float | None, interpretation: str = "", fmt: str = "auto") -> None:
    if fmt == "auto":
        if label.lower() in ("roe", "roic", "fcf yield", "fcf_yield", "operating_margin",
                             "net_margin", "revenue_growth", "shareholder_yield",
                             "incremental_roic", "gross_margin_stability", "croic"):
            formatted = fmt_pct(value)
        elif label.lower() in ("ev/ebit", "ev_ebit", "pb", "net_debt_to_ebitda",
                               "interest_coverage", "altman_zscore", "fcf_conversion"):
            formatted = fmt_ratio(value)
        elif label.lower() in ("dcf_value", "market_cap", "revenue", "net_income",
                               "fcf", "owner_earnings"):
            formatted = fmt_usd(value)
        else:
            formatted = fmt_ratio(value)
    else:
        formatted = str(value) if value is not None else "N/A"

    st.metric(label=label, value=formatted)
    if interpretation:
        st.caption(interpretation)


def metric_grid(metrics: dict[str, tuple[float | None, str]], cols: int = 4) -> None:
    items = list(metrics.items())
    rows = [items[i : i + cols] for i in range(0, len(items), cols)]

    for row in rows:
        columns = st.columns(cols)
        for col, (label, (value, interpretation)) in zip(columns, row):
            with col:
                metric_card(label, value, interpretation)
