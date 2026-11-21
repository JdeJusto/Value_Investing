"""Expense-line model, service semantics and CLI output."""

from __future__ import annotations

import json
from argparse import Namespace

import pytest

from backend.repositories.expense_lines import (
    EXPENSE_LINE_MAP,
    ExpenseLine,
    build_expense_lines,
)
from backend.services.expense_service import ExpenseReport, ExpenseService


def _fact(concept, value, currency="USD", namespace="us-gaap"):
    return {
        "concept": concept,
        "value": value,
        "currency": currency,
        "namespace": namespace,
        "unit": currency,
    }


def _line(lines, key):
    return next(line for line in lines if line.line_item == key)


def test_marketing_priority_prefers_marketing_over_advertising():
    facts = {
        "MarketingExpense": _fact("MarketingExpense", 20.0),
        "AdvertisingExpense": _fact("AdvertisingExpense", 10.0),
    }
    lines = build_expense_lines("X", 2025, facts)
    marketing = _line(lines, "marketing")
    assert marketing.value == 20.0
    assert marketing.source == "us-gaap:MarketingExpense"


def test_missing_line_is_undisclosed_not_zero():
    lines = build_expense_lines("X", 2025, {})
    marketing = _line(lines, "marketing")
    assert marketing.value is None
    assert marketing.is_disclosed is False
    assert marketing.reason == "no XBRL tag"


def test_override_none_forces_undisclosed():
    lines = build_expense_lines(
        "X",
        2025,
        {"AdvertisingExpense": _fact("AdvertisingExpense", 10.0)},
        overrides={"marketing": None},
    )
    marketing = _line(lines, "marketing")
    assert marketing.value is None
    assert marketing.is_disclosed is False
    assert "override" in marketing.reason


def test_override_numeric_is_verified_value():
    lines = build_expense_lines("X", 2025, {}, overrides={"marketing": 12.5})
    marketing = _line(lines, "marketing")
    assert marketing.value == 12.5
    assert marketing.source == "override:X"


def test_fx_conversion_and_missing_fx():
    fact = _fact("AdvertisingExpense", 100.0, currency="CNY")
    converted = build_expense_lines(
        "BABA", 2025, {"AdvertisingExpense": fact}, currency="CNY", fx_rate=0.14
    )
    assert _line(converted, "marketing").value == pytest.approx(14.0)

    missing = build_expense_lines(
        "BABA", 2025, {"AdvertisingExpense": fact}, currency="CNY", fx_rate=None
    )
    marketing = _line(missing, "marketing")
    assert marketing.is_disclosed is False
    assert "FX rate unavailable" in marketing.reason


def test_bank_lines_are_not_applicable():
    lines = build_expense_lines(
        "JPM", 2025, {}, not_applicable_reason="not applicable for banks"
    )
    assert all(not line.is_disclosed for line in lines)
    assert all("bank" in line.reason for line in lines)


def test_map_covers_expected_tags():
    assert "AdvertisingExpense" in EXPENSE_LINE_MAP["marketing"]
    assert "ResearchAndDevelopmentExpense" in EXPENSE_LINE_MAP["r_and_d"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_json_output(monkeypatch, capsys):
    report = ExpenseReport(
        ticker="KO",
        name="Coca-Cola",
        fiscal_year=2025,
        currency="USD",
        fx_rate=None,
        lines=[
            ExpenseLine(
                ticker="KO",
                fiscal_year=2025,
                line_item="marketing",
                label="Marketing / advertising",
                value=5_400_000_000.0,
                source="us-gaap:AdvertisingExpense",
                is_disclosed=True,
            )
        ],
    )

    class _FakeService:
        def build(self, ticker, fiscal_year=None):
            return report

    monkeypatch.setattr("cli.commands.expenses.ExpenseService", lambda: _FakeService())
    from cli.commands import expenses

    expenses._run(Namespace(ticker="KO", year=None, json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload["ticker"] == "KO"
    assert payload["lines"][0]["value"] == 5_400_000_000.0
    assert payload["lines"][0]["is_disclosed"] is True


# ---------------------------------------------------------------------------
# Live FDB (skipped when unavailable)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def service():
    from backend.repositories.financial_database_repository import (
        FinancialDatabaseRepository,
    )

    repo = FinancialDatabaseRepository()
    if not repo.available():
        pytest.skip("Financial-DataBase is not reachable")
    yield ExpenseService(repo)
    repo.close()


def test_ko_has_marketing_and_sga(service):
    report = service.build("KO", 2025)
    assert report is not None
    assert report.applicable
    marketing = _line(report.lines, "marketing")
    sga = _line(report.lines, "sga")
    assert marketing.is_disclosed and marketing.value > 0
    assert sga.is_disclosed and sga.value > 0


def test_apple_has_rnd_and_no_electricity(service):
    report = service.build("AAPL", 2026)
    assert report is not None
    assert _line(report.lines, "r_and_d").is_disclosed
    assert not _line(report.lines, "utilities").is_disclosed


def test_jpm_is_not_applicable(service):
    report = service.build("JPM")
    assert report is not None
    assert report.applicable is False
    assert all(not line.is_disclosed for line in report.lines)
