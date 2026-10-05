"""The Financials tab: full FDB facts per statement and year (demo mode)."""

from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "02_analysis.py"
DEMO_FINANCIALS = Path(__file__).resolve().parents[2] / "data" / "demo" / "financials"


def _run(monkeypatch) -> AppTest:
    monkeypatch.setenv("VI_DEMO", "1")
    at = AppTest.from_file(str(PAGE), default_timeout=120)
    at.run()
    next(button for button in at.button if button.label == "Analyze").click()
    at.run()
    assert not at.exception, at.exception
    return at


def _financial_frames(at):
    return [
        element.value
        for element in at.dataframe
        if "Concept" in list(element.value.columns)
    ]


def test_financials_tab_sits_before_raw(monkeypatch):
    at = _run(monkeypatch)
    main_labels = {
        "Overview",
        "Methodologies",
        "DCF",
        "Historical",
        "Filings",
        "Financials",
        "Raw",
    }
    labels = [tab.label for tab in at.tabs if tab.label in main_labels]
    assert labels == [
        "Overview",
        "Methodologies",
        "DCF",
        "Historical",
        "Filings",
        "Financials",
        "Raw",
    ]


def test_filters_are_present(monkeypatch):
    at = _run(monkeypatch)
    period = next(radio for radio in at.radio if radio.label == "Fiscal period")
    assert list(period.options) == ["FY", "Q1", "Q2", "Q3", "Q4"]
    years = next(
        field for field in at.number_input if field.label == "Show last N years"
    )
    assert years.value == 10
    units = next(field for field in at.multiselect if field.label == "Unit")
    assert "USD" in units.value


def test_one_column_per_fiscal_year(monkeypatch):
    at = _run(monkeypatch)
    frames = _financial_frames(at)
    assert frames, "the Financials tables must render"
    year_columns = [str(c) for c in frames[0].columns if str(c).startswith("FY")]
    assert year_columns == [f"FY{year}" for year in range(2025, 2015, -1)]


def test_income_statement_rows_render(monkeypatch):
    at = _run(monkeypatch)
    frames = _financial_frames(at)
    income = next(
        frame for frame in frames if (frame["Concept"] == "NetIncomeLoss").any()
    )
    row = income[income["Concept"] == "NetIncomeLoss"].iloc[0]
    assert row["Label"] == "Net Income"
    assert row["FY2025"].startswith("$")
    assert row["Unit"] == "USD"


def test_search_filters_the_visible_rows(monkeypatch):
    at = _run(monkeypatch)
    search = next(field for field in at.text_input if field.label == "Search concepts")
    search.set_value("NetIncomeLoss")
    at.run()
    assert not at.exception, at.exception
    frames = _financial_frames(at)
    assert len(frames) == 1  # only the income statement has a match
    assert list(frames[0]["Concept"]) == ["NetIncomeLoss"]
    assert any("Sin filas" in info.value for info in at.info)


def test_unit_filter_hides_rare_units(monkeypatch):
    at = _run(monkeypatch)
    units = next(field for field in at.multiselect if field.label == "Unit")
    units.set_value(["USD"])
    at.run()
    assert not at.exception, at.exception
    concepts = {
        concept for frame in _financial_frames(at) for concept in frame["Concept"]
    }
    assert "NetIncomeLoss" in concepts  # USD rows stay
    assert "CommonStockSharesAuthorized" not in concepts  # shares rows hidden


def test_csv_export_reflects_the_filtered_rows(monkeypatch):
    from backend.services.financials_view_service import (
        FinancialsViewService,
        filter_rows,
        table_rows,
    )
    from ui._shared import rows_to_csv

    monkeypatch.setenv("VI_DEMO", "1")
    view = FinancialsViewService().build("AAPL", "FY", 10)
    assert view is not None
    rows = filter_rows(view.income_statement, query="net income")
    csv_text = rows_to_csv(table_rows(rows, view.years))
    assert "NetIncomeLoss" in csv_text
    assert "Revenues" not in csv_text
    assert "FY2025" in csv_text


def test_demo_fixtures_are_capped():
    for ticker in ("AAPL", "KO", "JNJ", "JPM"):
        path = DEMO_FINANCIALS / f"{ticker}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = sum(
            len(payload[bucket])
            for bucket in (
                "balance_sheet",
                "income_statement",
                "cash_flow",
                "other",
            )
        )
        assert rows <= 100
        assert len(payload["years"]) == 10
        assert "Demo fixture" in payload["note"]
        assert path.stat().st_size < 40 * 1024


def test_each_subtab_has_a_csv_download(monkeypatch):
    at = _run(monkeypatch)
    buttons = at.get("download_button")
    assert len(buttons) >= 4  # one per statement sub-tab


def _summary_frame(at):
    summary = next(expander for expander in at.expander if expander.label == "Summary")
    return summary.dataframe[0].value


def test_summary_panel_renders_with_the_insight_columns(monkeypatch):
    at = _run(monkeypatch)
    frame = _summary_frame(at)
    assert list(frame.columns) == [
        "Metric",
        "Latest",
        "YoY",
        "5y CAGR",
        "Trend",
        "Stability",
    ]
    assert "Revenue" in set(frame["Metric"])
    assert any("Computed from Financial-DataBase facts" in c.value for c in at.caption)


def test_summary_panel_loads_demo_insights(monkeypatch):
    at = _run(monkeypatch)
    frame = _summary_frame(at)
    revenue = frame[frame["Metric"] == "Revenue"].iloc[0]
    assert revenue["Trend"] == "growing"
    assert str(revenue["Latest"]).startswith("$")
    assert revenue["Stability"] in {"stable", "volatile"}


def test_summary_has_a_csv_download(monkeypatch):
    at = _run(monkeypatch)
    buttons = at.get("download_button")
    assert len(buttons) >= 5  # four statement tables + the summary


def test_summary_csv_export_reflects_the_insight_rows(monkeypatch):
    from backend.services.financial_insights_service import (
        insight_rows,
        load_demo_insights,
    )
    from ui._shared import rows_to_csv

    monkeypatch.setenv("VI_DEMO", "1")
    report = load_demo_insights("AAPL")
    assert report is not None
    csv_text = rows_to_csv(insight_rows(report))
    assert "Metric,Latest,YoY,5y CAGR,Trend,Stability" in csv_text
    assert "Revenue" in csv_text


def test_alerts_placeholder_is_reserved(monkeypatch):
    at = _run(monkeypatch)
    alerts = next(
        expander for expander in at.expander if expander.label == "Alerts (coming soon)"
    )
    text = " ".join(markdown.value for markdown in alerts.markdown)
    assert "Real-time alerts" in text
