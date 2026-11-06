"""CLI `financials`: flat balance view, JSON and derived markers."""

from __future__ import annotations

import io
import json
import sys
from dataclasses import replace
from typing import ClassVar

import pytest

from backend.services import cli_output
from backend.services.financials_view_service import FinancialsRow, FinancialsView
from cli.commands import financials
from cli.main import main


class _TTY(io.StringIO):
    def isatty(self) -> bool:  # pragma: no cover - trivial
        return True


def _row(concept: str, label: str, value: str) -> FinancialsRow:
    return FinancialsRow(
        concept=concept,
        label=label,
        values={2025: value},
        unit="USD",
    )


def _view(*, derived: bool = False, partial_equity: bool = False) -> FinancialsView:
    rows = [
        _row("Assets", "Assets", "$100"),
        _row("AssetsCurrent", "Assets Current", "$60"),
        _row("Liabilities", "Liabilities", "$40"),
    ]
    if partial_equity:
        rows.append(_row("RetainedEarnings", "Retained Earnings", "$60"))
    else:
        rows.append(_row("StockholdersEquity", "Stockholders Equity", "$60"))
    rows.append(
        _row("LiabilitiesAndStockholdersEquity", "Liabilities and Equity", "$100")
    )
    return FinancialsView(
        ticker="AAPL",
        company_name="Apple Inc.",
        fiscal_period="FY",
        years=[2025],
        balance_sheet=rows,
        income_statement=[],
        cash_flow=[],
        other=[],
        unmatched_count=0,
        extraction_warnings=[],
        derived_liability_years=[2025] if derived else [],
    )


def _json_view() -> FinancialsView:
    rows = [
        _row("CashAndCashEquivalentsAtCarryingValue", "Cash", "$10"),
        _row("AccountsReceivableNetCurrent", "Receivables", "$20"),
        _row("InventoryNet", "Inventory", "$15"),
        _row("OtherAssetsCurrent", "Other current assets", "$5"),
        _row("ShortTermInvestments", "Short-term investments", "$10"),
        _row("AssetsCurrent", "Current Assets", "$60"),
        _row("PropertyPlantAndEquipmentNet", "Property, plant and equipment", "$40"),
        _row("AssetsNoncurrent", "Noncurrent Assets", "$40"),
        _row("Assets", "Assets", "$100"),
        _row("AccountsPayableCurrent", "Accounts payable", "$15"),
        _row("LiabilitiesCurrent", "Current Liabilities", "$25"),
        _row("LiabilitiesNoncurrent", "Noncurrent Liabilities", "$15"),
        _row("Liabilities", "Liabilities", "$40"),
        _row("CommonStockValue", "Common stock", "$5"),
        _row("AdditionalPaidInCapital", "Additional paid-in capital", "$25"),
        _row("RetainedEarningsAccumulatedDeficit", "Retained earnings", "$30"),
        _row("StockholdersEquity", "Stockholders Equity", "$60"),
        _row("LiabilitiesAndStockholdersEquity", "Liabilities and Equity", "$100"),
    ]
    return FinancialsView(
        ticker="AAPL",
        company_name="Apple Inc.",
        fiscal_period="FY",
        years=[2025],
        balance_sheet=rows,
        income_statement=[],
        cash_flow=[],
        other=[],
        unmatched_count=0,
        extraction_warnings=[],
        derived_liability_years=[],
    )


class _Service:
    view: FinancialsView | None = _view()
    calls: ClassVar[list[tuple]] = []

    def fetch_facts(self, ticker, period="FY", max_years=1):
        return []

    def build(self, ticker, period="FY", max_years=1, facts=None):
        type(self).calls.append((ticker, period, max_years))
        return type(self).view


@pytest.fixture(autouse=True)
def _patch_service(monkeypatch):
    cli_output.reset_no_color()
    _Service.view = _view()
    _Service.calls = []
    monkeypatch.setattr(financials, "FinancialsViewService", _Service)
    yield
    cli_output.reset_no_color()


def _run(*argv):
    sys.argv = ["main.py", *argv]
    main()


def test_financials_renders_five_sections(capsys):
    _Service.view = _json_view()
    _run("financials", "AAPL", "--no-color")

    out = capsys.readouterr().out
    for header in (
        "CURRENT ASSETS",
        "NON-CURRENT ASSETS",
        "CURRENT LIABILITIES",
        "NON-CURRENT LIABILITIES",
        "SHAREHOLDERS' EQUITY",
    ):
        assert header in out
    for subtotal in (
        "Total current assets",
        "Total non-current assets",
        "Total current liabilities",
        "Total non-current liabilities",
        "Total shareholders' equity",
    ):
        assert subtotal in out
    assert "TOTAL ASSETS" in out
    assert "TOTAL LIABILITIES + EQUITY" in out
    assert "Balanced" in out


def test_financials_excludes_subtotal_concepts_from_items(capsys):
    _Service.view = _json_view()
    _run("financials", "AAPL", "--no-color")

    out = capsys.readouterr().out
    # Subtotals are rendered as "Total ...", never as ordinary line items.
    assert "Current Assets" not in out
    assert "Noncurrent Assets" not in out
    assert "Current Liabilities" not in out
    assert "Noncurrent Liabilities" not in out
    assert "Stockholders Equity" not in out


def test_financials_json_contract_unchanged(capsys):
    _Service.view = _json_view()
    _run("financials", "AAPL", "--json")

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) >= {
        "ticker",
        "company_name",
        "fiscal_period",
        "fiscal_year",
        "assets",
        "liabilities_equity",
        "derived",
        "balanced",
        "delta",
        "balance_sheet",
    }
    assert payload["assets"]["total_current"] == 60.0
    assert payload["assets"]["total_non_current"] == 40.0
    assert payload["assets"]["total"] == 100.0
    assert payload["liabilities_equity"]["total_current"] == 25.0
    assert payload["liabilities_equity"]["total_non_current"] == 15.0
    assert payload["liabilities_equity"]["total_equity"] == 60.0
    assert payload["balanced"] is True


def test_financials_renders_both_sections(capsys):
    _run("financials", "AAPL")

    out = capsys.readouterr().out
    assert "Financials · AAPL" in out
    assert "ASSETS" in out
    assert "LIABILITIES + EQUITY" in out
    assert "$100" in out
    assert _Service.calls == [("AAPL", "FY", 5)]


def test_phantom_year_is_skipped(capsys):
    from dataclasses import replace

    _Service.view = replace(_view(), years=[2026, 2025])
    _run("financials", "AAPL", "--no-color")

    assert "FY2025" in capsys.readouterr().out


def test_years_limits_the_service_window(capsys):
    _run("financials", "AAPL", "--years", "3")

    assert _Service.calls[-1] == ("AAPL", "FY", 3)
    assert "AAPL" in capsys.readouterr().out


def test_json_output_is_valid(capsys):
    _run("financials", "AAPL", "--json")

    payload = json.loads(capsys.readouterr().out)
    assert payload["ticker"] == "AAPL"
    assert payload["fiscal_year"] == 2025
    assert payload["assets"]["total"] == 100.0
    assert payload["balanced"] is True


def test_derived_liabilities_get_the_marker_and_caption(capsys):
    _Service.view = _view(derived=True)
    _run("financials", "AAPL", "--no-color")

    out = capsys.readouterr().out
    assert "TOTAL LIABILITIES" in out
    assert "*" in out
    assert "Derived (Assets − Equity)" in out


def test_partial_equity_gets_its_own_caption(capsys):
    _Service.view = _view(partial_equity=True)
    _run("financials", "AAPL", "--no-color")

    out = capsys.readouterr().out
    assert "Partial equity (RetainedEarnings only; full equity not reported)" in out
    assert "TOTAL EQUITY *" in out


def test_no_color_disables_ansi(monkeypatch):
    out = _TTY()
    monkeypatch.setattr(sys, "stdout", out)
    _run("financials", "AAPL", "--no-color")

    assert "\x1b[" not in out.getvalue()


def test_no_color_before_the_subcommand(monkeypatch):
    out = _TTY()
    monkeypatch.setattr(sys, "stdout", out)
    _run("--no-color", "financials", "AAPL")

    assert "\x1b[" not in out.getvalue()


def test_unknown_ticker_exits_two(capsys):
    _Service.view = None
    with pytest.raises(SystemExit) as excinfo:
        _run("financials", "ZZZZ")

    assert excinfo.value.code == 2
    assert "No financial facts stored" in capsys.readouterr().out


def test_financials_json_has_grouped_line_items(capsys):
    _Service.view = _json_view()
    _run("financials", "AAPL", "--json")

    payload = json.loads(capsys.readouterr().out)
    assert len(payload["assets"]["current"]) >= 5
    assert len(payload["assets"]["non_current"]) >= 1
    assert len(payload["liabilities_equity"]["equity"]) >= 1
    assert payload["assets"]["total_current"] == 60.0
    assert payload["liabilities_equity"]["total_equity"] == 60.0
    assert "balance_sheet" in payload


def test_financials_json_assets_count_matches_render(capsys):
    _Service.view = _json_view()
    _run("financials", "AAPL", "--json")
    payload = json.loads(capsys.readouterr().out)
    _run("financials", "AAPL", "--no-color")
    output = capsys.readouterr().out

    for item in payload["assets"]["current"]:
        assert item["label"] in output


def test_financials_json_derived_flags(capsys):
    _Service.view = replace(_view(), derived_liability_years=[2025])
    _run("financials", "AAPL", "--json")
    assert json.loads(capsys.readouterr().out)["derived"]["liabilities"] is True

    _Service.view = _view(partial_equity=True)
    _run("financials", "AAPL", "--json")
    assert json.loads(capsys.readouterr().out)["derived"]["equity"] is True


def test_financials_json_balanced_chip_matches(capsys):
    _Service.view = _json_view()
    _run("financials", "AAPL", "--json")
    payload = json.loads(capsys.readouterr().out)

    assert payload["balanced"] is True
    assert abs(payload["delta"]) < 1e-6
