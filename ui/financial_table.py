"""Shared flat-table rendering for the financial statements.

Transversal readability pass (Balance Sheet "Vista tabla", Income
Statement, Cash Flow and Other):

* **Labels** — the ``Label`` column shows the ES name from
  ``ui.theme.labels`` when known, falling back to the backend
  humanization. The flat tables then speak the same language as the
  T view; the technical XBRL tag keeps living in the ``Concept``
  column (drives search and the CSV export).
* **Gaps** — an empty fiscal-year cell renders as the shared ``DASH``
  ("—"), never blank: absent data must not read as a real zero.
* **Density / affordances** — long tables get a bounded height with
  their own scrollbar instead of stretching the page, and the
  ``Unit`` / ``Concept`` columns carry ``column_config`` help text.

Values keep the backend's statement format ("$35.93B", "(7,172)",
"0.15"): the filing format is preserved end to end, including the CSV
export, which shows exactly what the table shows.
"""

from __future__ import annotations

import streamlit as st

from backend.services.financials_view_service import FinancialsRow
from ui._shared import dataframe_with_download
from ui.theme.format import DASH
from ui.theme.labels import label as field_label

#: Above this row count the grid gets a fixed height (internal scrollbar)
#: so a 40+ concept statement does not stretch the whole tab.
MAX_NATURAL_ROWS = 18
TABLE_MAX_HEIGHT = 640

COLUMN_HELP = {
    "Unit": "Unidad del hecho (USD, shares, USD/shares, pure)",
    "Concept": "Etiqueta XBRL original — se usa en la búsqueda y en el CSV",
}


def financial_table_rows(
    rows: list[FinancialsRow], years: list[int]
) -> list[dict[str, str]]:
    """Display rows for the flat statements: ES labels, DASH for gaps.

    Pure and testable: values and units are copied verbatim; only the
    ``Label`` column (FIELD_LABELS ES, humanization fallback) and empty
    cells (DASH) change with respect to ``table_rows``.
    """
    display: list[dict[str, str]] = []
    for row in rows:
        display.append(
            {
                "Label": field_label(row.concept),
                **{f"FY{year}": (row.values.get(year) or DASH) for year in years},
                "Unit": row.unit,
                "Concept": row.concept,
            }
        )
    return display


def financial_table(
    rows: list[FinancialsRow],
    years: list[int],
    filename: str,
    key: str,
) -> None:
    """Render one statement sub-tab (flat table + CSV download).

    Empty ``rows`` keep the existing contract: an info message and no
    download button (delegated to ``dataframe_with_download``).
    """
    display = financial_table_rows(rows, years)
    height = TABLE_MAX_HEIGHT if len(display) > MAX_NATURAL_ROWS else None
    dataframe_with_download(
        display,
        filename,
        key,
        height=height,
        column_config={
            name: st.column_config.TextColumn(name, help=help_text)
            for name, help_text in COLUMN_HELP.items()
        },
    )
