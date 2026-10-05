"""FinancialInsightsService: growth, stability and edge cases (pure facts)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from backend.services.financial_insights_service import (
    FinancialInsightsService,
    _cagr,
    _trend,
    insight_rows,
    report_from_payload,
    report_to_payload,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "financials"


def _load(name: str) -> list[dict]:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [dict(fact, value=Decimal(str(fact["value"]))) for fact in raw]


def _report(facts, ticker="TEST", company_name="Test Co."):
    return FinancialInsightsService(facts, ticker, company_name).build()


def _metric(report, name):
    return next(insight for insight in report.metrics if insight.metric == name)


def _fact(concept: str, year: int, value: str) -> dict:
    return {
        "concept": concept,
        "fiscal_year": year,
        "fiscal_period": "FY",
        "value": value,
        "unit": "USD",
        "period_end": f"{year}-12-31",
        "namespace": "us-gaap",
        "frame": "",
    }


# ---------------------------------------------------------------------------
# growth / trend
# ---------------------------------------------------------------------------
def test_revenue_growing_from_real_apple_fixture():
    report = _report(_load("aapl_facts.json"), "AAPL", "Apple Inc.")
    revenue = _metric(report, "revenue")
    assert revenue.trend == "growing"
    assert revenue.yoy_change_pct is not None and revenue.yoy_change_pct > 0
    assert revenue.yoy_display.startswith("+")
    assert revenue.latest_year == 2025
    assert revenue.latest_value == "$416,161,000,000"


def test_revenue_declining_from_synthetic_fixture():
    report = _report(_load("insights_edge_cases.json"))
    revenue = _metric(report, "revenue")
    assert revenue.trend == "declining"
    assert revenue.cagr_5y is not None and revenue.cagr_5y < -5
    assert revenue.yoy_display.startswith("-")


def test_margin_is_stable_when_changes_are_flat():
    report = _report(_load("insights_edge_cases.json"))
    margin = _metric(report, "net_margin")
    assert margin.stability == "stable"
    assert margin.trend == "stable"
    assert margin.latest_value == "10.0%"
    assert margin.yoy_display == "+0.0pp"


def test_trend_uses_yoy_when_cagr_is_not_available():
    # The AAPL fixture only spans three years, so the 5y CAGR is None and the
    # trend falls back to the (positive) YoY change.
    report = _report(_load("aapl_facts.json"))
    net_income = _metric(report, "net_income")
    assert net_income.cagr_5y is None
    assert net_income.trend == "growing"


# ---------------------------------------------------------------------------
# notes / missing data
# ---------------------------------------------------------------------------
def test_loss_to_profit_adds_a_turnaround_note():
    facts = [
        {
            "concept": "NetIncomeLoss",
            "fiscal_year": year,
            "fiscal_period": "FY",
            "value": value,
            "unit": "USD",
            "period_end": f"{year}-12-31",
            "namespace": "us-gaap",
            "frame": "",
        }
        for year, value in ((2023, "-10"), (2024, "50"))
    ]
    report = _report(facts)
    net_income = _metric(report, "net_income")
    assert "turnaround from loss to profit" in net_income.notes


def test_profit_to_loss_adds_a_note():
    facts = [
        {
            "concept": "NetIncomeLoss",
            "fiscal_year": year,
            "fiscal_period": "FY",
            "value": value,
            "unit": "USD",
            "period_end": f"{year}-12-31",
            "namespace": "us-gaap",
            "frame": "",
        }
        for year, value in ((2023, "10"), (2024, "-50"))
    ]
    report = _report(facts)
    net_income = _metric(report, "net_income")
    assert "profit to loss" in net_income.notes
    assert "negative value" in net_income.notes


def test_missing_metric_is_not_reported():
    report = _report(_load("aapl_facts.json"))
    dividends = _metric(report, "dividends_paid")
    assert dividends.latest_value == "—"
    assert dividends.latest_year is None
    assert dividends.yoy_change_pct is None
    assert dividends.cagr_5y is None
    assert dividends.notes == ["not reported"]


def test_no_facts_report_warns_and_every_metric_is_missing():
    report = _report([])
    assert report.warnings == ["no facts available for this company"]
    assert all(insight.latest_value == "—" for insight in report.metrics)


# ---------------------------------------------------------------------------
# computation rules
# ---------------------------------------------------------------------------
def test_cagr_is_none_when_the_base_is_not_positive():
    report = _report(_load("insights_edge_cases.json"))
    gross_profit = _metric(report, "gross_profit")
    # 2019 gross profit is -5, so the 5-year base is not positive.
    assert gross_profit.cagr_5y is None
    assert gross_profit.cagr_5y_display == "—"


def test_cagr_is_none_for_non_positive_endpoints():
    series = {
        2020: 100.0,
        2021: 110.0,
        2022: 120.0,
        2023: 130.0,
        2024: 140.0,
        2025: 150.0,
    }
    assert isinstance(_cagr(series, 5), float)  # normal positive case
    assert _cagr({**series, 2020: 0.0}, 5) is None  # base == 0
    assert _cagr({**series, 2020: -100.0}, 5) is None  # base < 0
    assert _cagr({**series, 2025: -150.0}, 5) is None  # latest < 0 (complex)
    assert _cagr({**series, 2025: 0.0}, 5) is None  # latest == 0


def test_metric_with_negative_latest_does_not_raise():
    """Regression (BA/WFC/INTC): positive base, negative latest year.

    Before the guard, ``(latest / base) ** (1 / span)`` was complex and the
    trend comparison raised ``TypeError: '>' not supported between
    instances of 'complex' and 'int'``.
    """
    facts = [
        _fact("NetIncomeLoss", year, value)
        for year, value in (
            (2020, "100"),
            (2021, "90"),
            (2022, "80"),
            (2023, "70"),
            (2024, "60"),
            (2025, "-10"),
        )
    ]
    report = _report(facts)  # must not raise
    net_income = _metric(report, "net_income")
    assert net_income.cagr_5y is None
    assert net_income.cagr_5y_display == "—"
    assert net_income.trend in {"growing", "stable", "declining"}
    assert net_income.yoy_display.startswith("-")  # 60 -> -10


def test_turnaround_with_a_loss_base_falls_back_to_yoy():
    facts = [
        _fact("NetIncomeLoss", year, value)
        for year, value in (
            (2020, "-50"),
            (2021, "10"),
            (2022, "20"),
            (2023, "30"),
            (2024, "40"),
            (2025, "50"),
        )
    ]
    report = _report(facts)
    net_income = _metric(report, "net_income")
    assert net_income.cagr_5y is None  # the base year is a loss
    assert net_income.trend == "growing"  # falls back to the +25% YoY


def test_trend_defends_against_a_complex_cagr():
    """Belt-and-braces: a complex value must never crash the comparisons."""
    assert _trend("currency", 1 + 2j, 5.0, {2024: 1.0, 2025: 2.0}) in {
        "growing",
        "stable",
        "declining",
    }


def test_yoy_is_none_when_the_prior_year_is_zero():
    report = _report(_load("insights_edge_cases.json"))
    dividends = _metric(report, "dividends_paid")
    assert dividends.yoy_change_pct is None
    assert dividends.yoy_display == "—"
    assert dividends.latest_value == "$5"


def test_free_cash_flow_is_ocf_minus_capex():
    facts = [
        {
            "concept": concept,
            "fiscal_year": 2024,
            "fiscal_period": "FY",
            "value": value,
            "unit": "USD",
            "period_end": "2024-12-31",
            "namespace": "us-gaap",
            "frame": "",
        }
        for concept, value in (
            ("NetCashProvidedByUsedInOperatingActivities", "100"),
            ("PaymentsToAcquirePropertyPlantAndEquipment", "30"),
        )
    ]
    report = _report(facts)
    fcf = _metric(report, "free_cash_flow")
    assert fcf.latest_value == "$70"


def test_build_is_deterministic():
    facts = _load("insights_edge_cases.json")
    assert _report(facts) == _report(facts)


# ---------------------------------------------------------------------------
# table rows + demo payload
# ---------------------------------------------------------------------------
def test_insight_rows_have_the_panel_columns():
    report = _report(_load("aapl_facts.json"), "AAPL", "Apple Inc.")
    rows = insight_rows(report)
    assert list(rows[0].keys()) == [
        "Metric",
        "Latest",
        "YoY",
        "5y CAGR",
        "Trend",
        "Stability",
    ]
    revenue = next(row for row in rows if row["Metric"] == "Revenue")
    assert revenue["Trend"] == "growing"
    assert revenue["Latest"].startswith("$")


def test_demo_payload_roundtrip_preserves_display_fields():
    report = _report(_load("insights_edge_cases.json"), "TEST", "Test Co.")
    payload = report_to_payload(report)
    restored = report_from_payload(payload)
    assert restored.ticker == "TEST"
    assert restored.company_name == "Test Co."
    assert len(restored.metrics) == len(report.metrics)
    original = _metric(report, "revenue")
    copy = next(row for row in restored.metrics if row.metric == "revenue")
    assert copy.latest_value == original.latest_value
    assert copy.yoy_display == original.yoy_display
    assert copy.cagr_5y_display == original.cagr_5y_display
    assert copy.trend == original.trend


def test_demo_insights_loader_reads_the_fixture(monkeypatch, tmp_path):
    import backend.services.financial_insights_service as module

    demo = tmp_path / "financials"
    demo.mkdir()
    payload = report_to_payload(_report(_load("insights_edge_cases.json"), "TEST"))
    (demo / "TEST_insights.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(module, "DEMO_ROOT", tmp_path)

    report = module.load_demo_insights("TEST")
    assert report is not None
    assert report.ticker == "TEST"
    assert module.load_demo_insights("ZZZZ") is None
