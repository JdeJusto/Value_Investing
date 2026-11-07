"""Pure plotly figure builders for the Streamlit Scorecard tab.

Kept out of the page so the data shaping is unit-testable without a Streamlit
runtime. The page owns rendering and the "plotly missing" fallback; the
builders here only turn an already-computed payload into a figure.

Everything is presentation: the values come from ``ScorecardChartService``
(fundamentals history) and the frozen scorecard payload (dimension scores).
"""

from __future__ import annotations

from typing import Any

#: The radar's radius scale (dimension scores are 0-10).
RADAR_RANGE = (0, 10)

#: P/E values outside this band are hidden from the Historical line chart;
#: the table/JSON keep the exact value. Near-zero earnings and share-scale
#: bugs otherwise flatten every other year in the chart.
PE_CHART_CAP = 100.0


def split_pe_outliers(
    rows: list[dict[str, Any]], cap: float = PE_CHART_CAP
) -> tuple[list[dict[str, Any]], int]:
    """Return ``(chart_rows, hidden_count)`` for the Historical P/E chart."""
    kept = [
        row
        for row in rows
        if row.get("P/E") is not None and abs(float(row["P/E"])) <= cap
    ]
    return kept, len(rows) - len(kept)


def radar_data(
    dimensions: list[dict[str, Any]],
) -> tuple[list[str], list[float | None]]:
    """Return the radar's ``(labels, radii)``.

    A dimension with no score stays ``None`` (a gap), never ``0``: missing is
    not the same as bad.
    """
    labels = [dimension["label"] for dimension in dimensions]
    radii = [dimension.get("score") for dimension in dimensions]
    return labels, radii


def radar_missing(labels: list[str], radii: list[float | None]) -> list[str]:
    """Labels of the axes that could not be scored (the radar's gaps)."""
    return [
        label for label, radius in zip(labels, radii, strict=True) if radius is None
    ]


def radar_figure(dimensions: list[dict[str, Any]]) -> Any:
    """Six-axis plotly radar of the dimension scores (0-10)."""
    import plotly.graph_objects as go

    from ui.theme.plotly_template import NEON_CYAN

    labels, radii = radar_data(dimensions)
    closed_labels = [*labels, labels[0]]
    closed_radii = [*radii, radii[0]]
    has_gap = any(radius is None for radius in radii)
    figure = go.Figure(
        go.Scatterpolar(
            r=closed_radii,
            theta=closed_labels,
            mode="lines+markers",
            connectgaps=False,
            fill=None if has_gap else "toself",
            line={"color": NEON_CYAN, "width": 2},
            marker={"size": 7, "color": NEON_CYAN},
            name="Score",
            hovertemplate="%{theta}: %{r}/10<extra></extra>",
        )
    )
    figure.update_layout(
        polar={
            "radialaxis": {
                "range": list(RADAR_RANGE),
                "tickvals": [0, 2, 4, 6, 8, 10],
                "visible": True,
            }
        },
        showlegend=False,
        height=380,
        margin={"l": 50, "r": 50, "t": 30, "b": 30},
    )
    return figure


def _fiscal_years(payload: dict[str, Any]) -> list[int]:
    return [year["fiscal_year"] for year in payload.get("years", [])]


def _column(payload: dict[str, Any], key: str) -> list[float | None]:
    return [year.get(key) for year in payload.get("years", [])]


def _has_any(*columns: list[float | None]) -> bool:
    return any(value is not None for column in columns for value in column)


def _style(figure: Any, *, y_title: str, percent: bool = False) -> Any:
    figure.update_layout(
        height=320,
        margin={"l": 50, "r": 20, "t": 30, "b": 30},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        hovermode="x unified",
    )
    figure.update_yaxes(title_text=y_title)
    if percent:
        figure.update_yaxes(tickformat=".0%")
    return figure


def revenue_income_figure(payload: dict[str, Any]) -> Any | None:
    """Revenue and net income bars, one pair per fiscal year."""
    import plotly.graph_objects as go

    revenue = _column(payload, "revenue")
    net_income = _column(payload, "net_income")
    if not _has_any(revenue, net_income):
        return None
    years = _fiscal_years(payload)
    figure = go.Figure()
    figure.add_bar(x=years, y=revenue, name="Revenue")
    figure.add_bar(x=years, y=net_income, name="Net income")
    figure.update_layout(barmode="group")
    return _style(figure, y_title="USD")


def margin_figure(payload: dict[str, Any]) -> Any | None:
    """Gross / operating / net margin lines (fractions, shown as %)."""
    import plotly.graph_objects as go

    gross = _column(payload, "gross_margin")
    operating = _column(payload, "operating_margin")
    net = _column(payload, "net_margin")
    if not _has_any(gross, operating, net):
        return None
    years = _fiscal_years(payload)
    figure = go.Figure()
    figure.add_scatter(x=years, y=gross, name="Gross margin", mode="lines+markers")
    figure.add_scatter(
        x=years, y=operating, name="Operating margin", mode="lines+markers"
    )
    figure.add_scatter(x=years, y=net, name="Net margin", mode="lines+markers")
    return _style(figure, y_title="Margin", percent=True)


def returns_figure(payload: dict[str, Any]) -> Any | None:
    """ROE and ROIC lines (fractions, shown as %)."""
    import plotly.graph_objects as go

    roe = _column(payload, "roe")
    roic = _column(payload, "roic")
    if not _has_any(roe, roic):
        return None
    years = _fiscal_years(payload)
    figure = go.Figure()
    figure.add_scatter(x=years, y=roe, name="ROE", mode="lines+markers")
    figure.add_scatter(x=years, y=roic, name="ROIC", mode="lines+markers")
    return _style(figure, y_title="Return", percent=True)


def value_vs_price_figure(payload: dict[str, Any]) -> Any | None:
    """DCF intrinsic value vs current price, per share.

    Returns ``None`` when either side is missing so the tab can show
    "price unavailable" instead of drawing a misleading single bar.
    """
    import plotly.graph_objects as go

    from ui.theme.plotly_template import CHROME, GOLD

    dcf_value = payload.get("dcf_value")
    price = payload.get("price")
    if dcf_value is None or price is None:
        return None
    figure = go.Figure(
        go.Bar(
            x=["DCF value", "Price"],
            y=[dcf_value, price],
            marker={"color": [GOLD, CHROME]},
            hovertemplate="%{x}: $%{y:,.2f}<extra></extra>",
        )
    )
    figure.update_layout(showlegend=False)
    return _style(figure, y_title="USD / share")


def pe_multiple(text: Any) -> float | None:
    """Parse a formatted P/E (``"15.50x"``) back into a number.

    The peer median travels as a display string (same formatting as the rule
    value), so the chart reads it back. Anything unparseable is ``None`` and
    the caller hides the chart.
    """
    if text is None:
        return None
    cleaned = str(text).strip().lower().removesuffix("x").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def peer_pe_values(card: dict[str, Any]) -> tuple[float, float, str | None] | None:
    """``(company P/E, peer median P/E, peer group)`` from a scorecard payload.

    ``None`` unless the valuation rule carries a peer percentile *and* both
    multiples parse: no artifact, no comparison.
    """
    for dimension in card.get("dimensions", []):
        for rule in dimension.get("rules", []):
            if rule.get("rule_id") != "pe_absolute":
                continue
            if rule.get("peer_percentile") is None:
                return None
            company = pe_multiple(rule.get("value"))
            median = pe_multiple(rule.get("peer_median"))
            if company is None or median is None or company <= 0 or median <= 0:
                return None
            return company, median, dimension.get("peer_group")
    return None


def peer_pe_figure(card: dict[str, Any]) -> Any | None:
    """Two bars: the company's P/E next to its peer group's median P/E.

    Deliberately its own small chart rather than a third bar on the DCF
    panel: the DCF bars are dollars per share and these are multiples.
    """
    values = peer_pe_values(card)
    if values is None:
        return None
    import plotly.graph_objects as go

    from ui.theme.plotly_template import CHROME, NEON_CYAN

    company, median, group = values
    peer_label = f"Peer median ({group})" if group else "Peer median"
    figure = go.Figure(
        go.Bar(
            x=[company, median],
            y=[str(card.get("ticker") or "Company"), peer_label],
            orientation="h",
            marker={"color": [NEON_CYAN, CHROME]},
            hovertemplate="%{y}: %{x:.2f}x<extra></extra>",
        )
    )
    figure.update_layout(showlegend=False)
    return _style(figure, y_title="")


#: Evolution tab: canonical core_financials fields and their labels.
EVOLUTION_FIELDS = (
    ("revenue", "Revenue"),
    ("net_income", "Net income"),
    ("operating_income", "Operating income"),
    ("gross_profit", "Gross profit"),
    ("total_assets", "Total assets"),
    ("total_liabilities", "Total liabilities"),
    ("stockholders_equity", "Shareholders' equity"),
    ("cash", "Cash"),
)


def evolution_has_history(
    timeseries: dict[str, list[tuple[int, float | None]]],
    min_years: int = 2,
) -> bool:
    """True when at least one field has ``min_years`` non-null observations."""
    return any(
        sum(1 for _year, value in timeseries.get(field, []) if value is not None)
        >= min_years
        for field, _label in EVOLUTION_FIELDS
    )


def evolution_figures(
    timeseries: dict[str, list[tuple[int, float | None]]],
) -> list[Any]:
    """Eight 10-year evolution figures (USD billions), in a stable order."""
    import plotly.graph_objects as go

    from ui.theme.plotly_template import (
        CHROME,
        GOLD,
        NEON_CYAN,
        NEON_LAVENDER,
        NEON_MINT,
        NEON_ORANGE,
        NEON_PINK,
        NEON_PURPLE,
    )

    colors = (
        NEON_CYAN,
        NEON_PINK,
        GOLD,
        CHROME,
        NEON_PURPLE,
        NEON_MINT,
        NEON_ORANGE,
        NEON_LAVENDER,
    )
    figures = []
    for (field, label), color in zip(EVOLUTION_FIELDS, colors, strict=True):
        rows = timeseries.get(field, [])
        years = [year for year, _value in rows]
        values = [
            value / 1_000_000_000 if value is not None else None
            for _year, value in rows
        ]
        figure = go.Figure(
            go.Scatter(
                x=years,
                y=values,
                mode="lines+markers",
                name=label,
                line={"color": color, "width": 2},
                marker={"size": 5, "color": color},
                hovertemplate="FY%{x}: $%{y:.2f}B<extra></extra>",
            )
        )
        figure.update_layout(
            title={"text": label, "font": {"size": 13}},
            showlegend=False,
            height=250,
        )
        _style(figure, y_title="USD B")
        figures.append(figure)
    return figures


#: Peers tab: canonical dimension order and labels (mirrors the scorecard).
PEER_DIMENSIONS = (
    ("growth", "Growth"),
    ("profitability", "Profitability"),
    ("financial_health", "Financial Health"),
    ("valuation", "Valuation"),
    ("shareholder_returns", "Shareholder Returns"),
    ("management_moat", "Management/Moat"),
)


def peer_dimension_rows(
    payload: dict[str, dict[str, int | None]],
) -> list[dict[str, Any]]:
    """Matrix rows (one per dimension) for ``st.dataframe``.

    Columns are the companies in payload order (the subject first). A missing
    score shows an em dash, never a zero.
    """
    tickers = list(payload)
    rows: list[dict[str, Any]] = []
    for key, label in PEER_DIMENSIONS:
        row: dict[str, Any] = {"Dimension": label}
        for ticker in tickers:
            score = payload[ticker].get(key)
            row[ticker] = "—" if score is None else f"{score}/10"
        rows.append(row)
    return rows


def peer_radar_figure(payload: dict[str, dict[str, int | None]]) -> Any | None:
    """One radar trace per company; the subject (first key) is highlighted."""
    if not payload:
        return None
    import plotly.graph_objects as go

    from ui.theme.plotly_template import (
        GOLD,
        NEON_CYAN,
        NEON_LAVENDER,
        NEON_MINT,
        NEON_ORANGE,
        NEON_PINK,
        NEON_PURPLE,
    )

    peer_colors = (
        NEON_PINK,
        GOLD,
        NEON_PURPLE,
        NEON_MINT,
        NEON_ORANGE,
        NEON_LAVENDER,
    )
    labels = [label for _key, label in PEER_DIMENSIONS]
    closed_labels = [*labels, labels[0]]
    figure = go.Figure()
    for index, (ticker, scores) in enumerate(payload.items()):
        radii = [scores.get(key) for key, _label in PEER_DIMENSIONS]
        closed_radii = [*radii, radii[0]]
        is_subject = index == 0
        color = NEON_CYAN if is_subject else peer_colors[(index - 1) % len(peer_colors)]
        has_gap = any(radius is None for radius in radii)
        figure.add_trace(
            go.Scatterpolar(
                r=closed_radii,
                theta=closed_labels,
                mode="lines+markers",
                connectgaps=False,
                fill="toself" if is_subject and not has_gap else None,
                fillcolor="rgba(0,240,255,0.12)"
                if is_subject and not has_gap
                else None,
                line={"color": color, "width": 2 if is_subject else 1},
                marker={"size": 6 if is_subject else 4, "color": color},
                name=ticker,
                hovertemplate=f"{ticker} · %{{theta}}: %{{r}}/10<extra></extra>",
            )
        )
    figure.update_layout(
        polar={
            "radialaxis": {
                "range": [0, 10],
                "tickvals": [0, 2, 4, 6, 8, 10],
                "visible": True,
            }
        },
        showlegend=True,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.05, "x": 0},
        height=460,
        margin={"l": 60, "r": 60, "t": 50, "b": 40},
    )
    return figure
