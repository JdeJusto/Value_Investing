"""CLI `financials`: flat balance view, JSON and derived markers."""

from __future__ import annotations

import io
import json
import sys
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


class _Service:
    view: FinancialsView | None = _view()
    calls: ClassVar[list[tuple]] = []

    def build(self, ticker, period="FY", max_years=1):
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
    assert payload["totals"]["assets"] == 100.0
    assert payload["totals"]["balanced"] is True


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
