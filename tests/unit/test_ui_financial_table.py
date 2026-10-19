"""Transversal readability pass over the flat financial tables.

``ui.financial_table`` is the shared renderer for the Balance Sheet
"Vista tabla", Income Statement, Cash Flow and Other sub-tabs: ES
labels, DASH for gaps, filing-format values untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.services.financials_view_service import FinancialsRow
from ui.financial_table import financial_table_rows
from ui.theme.format import DASH
from ui.theme.labels import FIELD_LABELS

REPO = Path(__file__).resolve().parents[2]
DEMO_FINANCIALS = REPO / "data" / "demo" / "financials"
PAGE = REPO / "ui" / "pages" / "02_analysis.py"


# ---------------------------------------------------------------------------
# financial_table_rows (pure)
# ---------------------------------------------------------------------------


def test_financial_table_rows_uses_es_labels_and_dash_for_gaps():
    rows = [
        FinancialsRow(
            concept="NetIncomeLoss",
            label="Net Income",
            values={2025: "$1.00B"},
            unit="USD",
        ),
    ]
    display = financial_table_rows(rows, [2025, 2024])

    assert list(display[0]) == ["Label", "FY2025", "FY2024", "Unit", "Concept"]
    assert display[0]["Label"] == "Resultado neto"  # FIELD_LABELS, ES
    assert display[0]["FY2025"] == "$1.00B"  # filing format preserved
    assert display[0]["FY2024"] == DASH  # gap never renders blank
    assert display[0]["Unit"] == "USD"
    assert display[0]["Concept"] == "NetIncomeLoss"  # search/CSV still work


def test_financial_table_rows_falls_back_to_humanization():
    rows = [
        FinancialsRow(
            concept="SomeUnknownTag",
            label="Some Unknown Tag",
            values={2025: "0.15"},
            unit="pure",
        ),
    ]
    display = financial_table_rows(rows, [2025])

    assert display[0]["Label"] == "Some Unknown Tag"
    assert display[0]["FY2025"] == "0.15"


def test_financial_table_rows_handles_empty_input():
    assert financial_table_rows([], [2025]) == []


# ---------------------------------------------------------------------------
# Label coverage across every demo fixture
# ---------------------------------------------------------------------------


def test_labels_cover_fixture_income_cash_and_other_concepts():
    """Every IS/CF/other concept in the demo fixtures has ES + EN labels."""
    fixtures: set[str] = set()
    for path in sorted(DEMO_FINANCIALS.glob("*.json")):
        if path.name.endswith(("_alerts.json", "_insights.json")):
            continue
        payload = json.loads(path.read_text())
        for bucket in ("income_statement", "cash_flow", "other"):
            fixtures |= {row["concept"] for row in payload.get(bucket, [])}

    unlabeled = sorted(
        concept
        for concept in fixtures
        if concept not in FIELD_LABELS
        or not FIELD_LABELS[concept].get("es")
        or not FIELD_LABELS[concept].get("en")
    )
    assert unlabeled == [], f"missing FIELD_LABELS entries: {unlabeled}"


# ---------------------------------------------------------------------------
# Financials tab integration (demo mode)
# ---------------------------------------------------------------------------


def test_flat_statement_tables_render_through_the_component(monkeypatch):
    """Income shows ES labels; the flat balance renders DASH for gaps."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("VI_DEMO", "1")
    at = AppTest.from_file(str(PAGE), default_timeout=120)
    at.run()
    next(button for button in at.button if button.label == "Analyze").click()
    at.run()
    assert not at.exception, at.exception

    frames = [
        element.value
        for element in at.dataframe
        if "Concept" in list(element.value.columns)
    ]

    # Income Statement: ES label, XBRL tag still in the Concept column.
    income = next(
        frame for frame in frames if (frame["Concept"] == "NetIncomeLoss").any()
    )
    label = income[income["Concept"] == "NetIncomeLoss"].iloc[0]["Label"]
    assert label == "Resultado neto"

    # Balance Sheet: switch to the flat view; gaps show DASH, not blanks.
    mode = next(radio for radio in at.radio if radio.label == "Vista")
    mode.set_value("Vista tabla")
    at.run()
    assert not at.exception, at.exception
    frames = [
        element.value
        for element in at.dataframe
        if "Concept" in list(element.value.columns)
    ]
    balance = next(
        frame for frame in frames if (frame["Concept"] == "AssetsNoncurrent").any()
    )
    row = balance[balance["Concept"] == "AssetsNoncurrent"].iloc[0]
    assert row["FY2025"] == "$211.28B"
    assert row["FY2017"] == DASH  # fixture covers 2018-2025 for this concept
