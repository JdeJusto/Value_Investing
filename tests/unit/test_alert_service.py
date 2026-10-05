"""AlertService: deterministic rules, skips and evidence (pure facts)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from backend.services.alert_service import RULES, AlertService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "financials"


def _load(name: str) -> list[dict]:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [dict(fact, value=Decimal(str(fact["value"]))) for fact in raw]


def _build(facts, ticker="TEST", company_name="Test Co.", fiscal_period="FY"):
    return AlertService(facts).build(ticker, company_name, fiscal_period)


def _fired(report, rule_id: str):
    return [alert for alert in report.alerts if alert.rule_id == rule_id]


def _fact(concept: str, year: int, value: str, unit: str = "USD") -> dict:
    return {
        "concept": concept,
        "fiscal_year": year,
        "fiscal_period": "FY",
        "value": value,
        "unit": unit,
        "period_end": f"{year}-12-31",
        "namespace": "us-gaap",
        "frame": "",
    }


# ---------------------------------------------------------------------------
# AAPL fixture
# ---------------------------------------------------------------------------
def test_aapl_fixture_fires_inventory_buildup_and_counts_skips():
    report = _build(_load("aapl_facts.json"), "AAPL", "Apple Inc.")
    fired = _fired(report, "inventory_buildup")
    assert len(fired) == 1
    assert fired[0].severity == "WARNING"
    assert fired[0].period == "FY2025"
    assert "Inventory growth" in fired[0].evidence
    # No debt and no dividend concepts in the fixture: those rules skip.
    assert report.rules_evaluated == len(RULES)
    assert report.rules_skipped == 2
    assert not _fired(report, "debt_spike")
    assert not _fired(report, "dividend_cut")


def test_every_alert_carries_evidence():
    report = _build(_load("aapl_facts.json"), "AAPL", "Apple Inc.")
    assert report.alerts
    for alert in report.alerts:
        assert alert.evidence, alert.rule_id
        assert all(str(value) for value in alert.evidence.values())


# ---------------------------------------------------------------------------
# synthetic declining / cash-poor company
# ---------------------------------------------------------------------------
def test_declining_company_fires_the_expected_rules():
    report = _build(_load("alerts_edge_cases.json"), "DWN", "Declining Co.")
    fired = {alert.rule_id for alert in report.alerts}
    assert fired == {
        "low_cash_runway",
        "margin_collapse",
        "debt_spike",
        "inventory_buildup",
        "negative_fcf_streak",
        "revenue_decline",
        "earnings_quality",
        "eps_dilution",
        "dividend_cut",
    }
    assert report.rules_skipped == 0  # every rule had data (rule 10 just did not fire)


def test_low_cash_runway_is_critical_with_months_of_evidence():
    report = _build(_load("alerts_edge_cases.json"))
    alert = _fired(report, "low_cash_runway")[0]
    assert alert.severity == "CRITICAL"
    assert alert.period == "FY2024"
    assert alert.evidence["Runway"] == "2.4 months"
    assert "6 months" in alert.message


def test_low_cash_runway_counts_short_term_investments():
    # MSFT-like: little cash but large short-term investments -> no alert.
    facts = [
        _fact("CashAndCashEquivalentsAtCarryingValue", 2024, "100"),
        _fact("ShortTermInvestments", 2024, "500"),
        _fact("OperatingExpenses", 2024, "500"),
    ]
    report = _build(facts)
    assert not _fired(report, "low_cash_runway")  # liquid 600 -> 14.4 months


def test_low_cash_runway_evidence_includes_investments_when_present():
    facts = [
        _fact("CashAndCashEquivalentsAtCarryingValue", 2024, "50"),
        _fact("ShortTermInvestments", 2024, "30"),
        _fact("OperatingExpenses", 2024, "500"),
    ]
    report = _build(facts)
    alert = _fired(report, "low_cash_runway")[0]
    assert alert.evidence["Short-term investments"] == "$30"
    assert alert.evidence["Runway"] == "1.9 months"


def test_margin_collapse_reports_the_pp_change():
    report = _build(_load("alerts_edge_cases.json"))
    alerts = _fired(report, "margin_collapse")
    assert len(alerts) == 1  # gross margin collapsed, net margin did not
    assert alerts[0].title == "Gross Margin collapse"
    assert alerts[0].evidence["Change"] == "-6.0pp"
    assert alerts[0].metric_hint == "gross_margin"


def test_severity_ordering_is_critical_warning_info():
    report = _build(_load("alerts_edge_cases.json"))
    severities = [alert.severity for alert in report.alerts]
    order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    assert severities == sorted(severities, key=lambda s: order[s])
    assert severities[0] == "CRITICAL"
    # Within a severity the rule_id keeps it deterministic.
    warnings = [a.rule_id for a in report.alerts if a.severity == "WARNING"]
    assert warnings == sorted(warnings)


# ---------------------------------------------------------------------------
# missing data and edge cases
# ---------------------------------------------------------------------------
def test_missing_data_skips_rules_silently():
    facts = [_fact("Revenues", 2024, "100"), _fact("Revenues", 2023, "90")]
    report = _build(facts)
    assert report.alerts == []
    assert report.rules_skipped == len(RULES) - 1  # only revenue_decline has data
    assert report.rules_evaluated == len(RULES)


def test_zero_prior_growth_does_not_fire():
    facts = [
        _fact("Revenues", 2024, "100"),
        _fact("Revenues", 2023, "0"),
    ]
    report = _build(facts)
    assert not _fired(report, "revenue_decline")


def test_strong_fcf_conversion_is_a_positive_info_alert():
    facts = (
        [
            _fact("NetIncomeLoss", year, ni)
            for year, ni in ((2022, "10"), (2023, "12"), (2024, "14"))
        ]
        + [
            _fact("NetCashProvidedByUsedInOperatingActivities", year, ocf)
            for year, ocf in ((2022, "15"), (2023, "18"), (2024, "20"))
        ]
        + [
            _fact("PaymentsToAcquirePropertyPlantAndEquipment", year, capex)
            for year, capex in ((2022, "2"), (2023, "2"), (2024, "2"))
        ]
    )
    report = _build(facts)
    alert = _fired(report, "strong_fcf_conversion")[0]
    assert alert.severity == "INFO"
    assert alert.evidence["FCF / net income"] == "1.29, 1.33, 1.30"


def test_inventory_floor_keeps_small_ticks_quiet():
    # TSLA-like: inventory +3.1% vs revenue -2.9% is below the 10% floor.
    facts = [
        _fact("InventoryNet", 2024, "103.1"),
        _fact("InventoryNet", 2023, "100"),
        _fact("Revenues", 2024, "97.1"),
        _fact("Revenues", 2023, "100"),
    ]
    report = _build(facts)
    assert not _fired(report, "inventory_buildup")


def test_quarterly_period_label():
    facts = [
        _fact("Revenues", 2024, "100"),
        _fact("Revenues", 2023, "90"),
        _fact("Revenues", 2022, "80"),
    ]
    report = _build(facts, fiscal_period="Q2")
    # No decline → no alert, but the period helper is exercised on evaluation.
    assert report.rules_evaluated == len(RULES)


def test_build_is_deterministic():
    facts = _load("alerts_edge_cases.json")
    assert _build(facts) == _build(facts)


def test_report_carries_ticker_and_company():
    report = _build(_load("alerts_edge_cases.json"), "DWN", "Declining Co.")
    assert report.ticker == "DWN"
    assert report.company_name == "Declining Co."


def test_demo_alerts_payload_roundtrip_and_loader(monkeypatch, tmp_path):
    import backend.services.alert_service as module

    report = _build(_load("alerts_edge_cases.json"), "DWN", "Declining Co.")
    payload = module.alerts_to_payload(report)
    restored = module.alerts_from_payload(payload)
    assert restored.ticker == "DWN"
    assert restored.rules_skipped == report.rules_skipped
    assert len(restored.alerts) == len(report.alerts)
    assert restored.alerts[0].evidence == report.alerts[0].evidence

    demo = tmp_path / "financials"
    demo.mkdir()
    (demo / "DWN_alerts.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(module, "DEMO_ROOT", tmp_path)
    loaded = module.load_demo_alerts("DWN")
    assert loaded is not None and loaded.alerts
    assert module.load_demo_alerts("ZZZZ") is None
