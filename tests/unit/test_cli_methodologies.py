"""Unit tests for the methodology CLI commands.

The commands are exercised through ``main()`` with patched argv, and the data
sources are replaced by fakes so no network or database is touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from cli.main import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class _Prices:
    """Minimal price stub with the one method the commands call."""

    def __init__(self, price=100.0):
        self._price = price
        self.calls = []

    def get_current_price(self, ticker):
        self.calls.append(ticker)
        return self._price


class _Repo:
    def __init__(self, fixture="graham_pass.json"):
        self._fixture = fixture

    def get_best_available(self, ticker):
        return _rows(self._fixture)


def _rows(name):
    from backend.domain.value_objects.financials_normalized import NormalizedFinancials

    return [
        NormalizedFinancials.from_dict(row)
        for row in json.loads((FIXTURES / name).read_text())
    ]


def _run(argv, monkeypatch, price=100.0, repo_fixture="graham_pass.json"):
    """Run the CLI with patched argv and data sources; returns stdout."""
    monkeypatch.setattr(sys, "argv", ["main.py"] + argv)
    monkeypatch.setattr(
        "backend.app.cli.build_financial_repository",
        lambda: _Repo(repo_fixture),
    )
    monkeypatch.setattr(
        "backend.services.price_service.get_price_service", lambda: _Prices(price)
    )
    main()


# ----------------------------------------------------------------------
# methodologies list
# ----------------------------------------------------------------------


def test_list_shows_graham(monkeypatch, capsys):
    _run(["methodologies", "list"], monkeypatch)
    out = capsys.readouterr().out
    assert "graham" in out
    assert "1.0.0" in out
    assert "DEEP_VALUE" in out


# ----------------------------------------------------------------------
# methodologies show
# ----------------------------------------------------------------------


def test_show_graham_renders_all_sections(monkeypatch, capsys):
    _run(["methodologies", "show", "graham"], monkeypatch)
    out = capsys.readouterr().out
    for section in ("Rules", "Verdict logic", "Known limitations", "Era adjustment"):
        assert section in out
    assert "graham.criterion_1_size" in out
    assert "The Intelligent Investor" in out
    assert "Ch. 14" in out


def test_show_unknown_methodology_reports_error(monkeypatch, capsys):
    _run(["methodologies", "show", "nonexistent"], monkeypatch)
    captured = capsys.readouterr()
    assert "unknown methodology" in captured.out
    assert "graham" in captured.out


# ----------------------------------------------------------------------
# analyze-graham
# ----------------------------------------------------------------------


def test_analyze_graham_renders_verdict_and_criteria(monkeypatch, capsys):
    _run(["analyze-graham", "AAPL"], monkeypatch)
    out = capsys.readouterr().out
    assert "Graham analysis" in out
    assert "AAPL" in out
    assert "Verdict" in out
    assert "Score" in out
    assert "Confidence" in out
    assert "Criteria" in out
    assert "Metrics" in out
    assert "Reasons" in out
    assert "Sources" in out


def test_analyze_graham_pass_fixture_is_buy(monkeypatch, capsys):
    _run(["analyze-graham", "AAPL"], monkeypatch)
    out = capsys.readouterr().out
    assert "BUY" in out


def test_analyze_graham_fail_fixture_is_avoid(monkeypatch, capsys):
    _run(["analyze-graham", "AAPL"], monkeypatch, repo_fixture="graham_fail.json")
    out = capsys.readouterr().out
    assert "AVOID" in out
    assert "Red flags" in out


def test_analyze_graham_era_adjustment_changes_size_threshold(monkeypatch, capsys):
    _run(["analyze-graham", "AAPL", "--era-adjustment"], monkeypatch)
    out = capsys.readouterr().out
    assert "era_adjustment_applied : True" in out
    assert "560,000,000" in out or "560000000" in out


def test_analyze_graham_without_era_adjustment_uses_book_threshold(monkeypatch, capsys):
    _run(["analyze-graham", "AAPL"], monkeypatch)
    out = capsys.readouterr().out
    assert "graham_modernized" not in out
    assert "era_adjustment_applied : False" in out


# ----------------------------------------------------------------------
# compare-methodologies
# ----------------------------------------------------------------------


def test_compare_with_two_methodologies_renders_cleanly(monkeypatch, capsys):
    _run(["compare-methodologies", "AAPL"], monkeypatch)
    out = capsys.readouterr().out
    assert "Methodology comparison" in out
    assert "graham" in out
    assert "buffett_clark" in out
    assert "Disagreement summary" in out


def test_compare_unknown_methodology_warns_and_skips(monkeypatch, capsys):
    _run(["compare-methodologies", "AAPL", "--methodologies", "graham,nonexistent"], monkeypatch)
    captured = capsys.readouterr()
    assert "unknown methodology 'nonexistent'" in captured.out
    assert "graham" in captured.out


def test_compare_renders_all_five_methodologies(monkeypatch, capsys):
    _run(["compare-methodologies", "AAPL"], monkeypatch)
    out = capsys.readouterr().out
    for name in (
        "buffett_clark",
        "buffett_classic",
        "fisher_quantitative_subset",
        "graham",
        "graham_dodd",
    ):
        assert name in out
    assert "Disagreement summary" in out


# ----------------------------------------------------------------------
# framework behaviour through the CLI
# ----------------------------------------------------------------------


def test_score_none_renders_as_em_dash(monkeypatch, capsys):
    """Decision 10: a methodology without a numeric scale renders —, not 0.0."""
    from backend.methodologies.base import Confidence, Methodology, MethodologyResult, Verdict

    class _NoScore(Methodology):
        name = "noscore"
        version = "1.0.0"
        family = "OTHER"

        def evaluate(self, ticker, fundamentals, prices):
            return MethodologyResult(
                methodology="noscore", version=self.version, family=self.family,
                verdict=Verdict.BUY, score=None, metrics={}, reasons=[],
                red_flags=[], confidence=Confidence.HIGH, sources=[],
            )

        def rules(self):
            return []

        def metadata(self):
            return {}

    import cli.commands.compare_methodologies as compare
    import sys

    # The package re-exports the singleton, so patch the real module object.
    registry_module = sys.modules["backend.methodologies.registry"]
    monkeypatch.setattr(registry_module, "discover", lambda: None)
    registry = registry_module.registry
    monkeypatch.setattr(
        registry, "get", lambda name: _NoScore() if name == "noscore" else None
    )
    monkeypatch.setattr(registry, "list", lambda: ["noscore"])

    _run(["compare-methodologies", "AAPL", "--methodologies", "noscore"], monkeypatch)
    out = capsys.readouterr().out
    assert "—" in out
    assert "BUY" in out


def test_no_price_means_no_network_and_no_db(monkeypatch, capsys):
    """The methodology only reads what it is handed."""
    _run(["analyze-graham", "AAPL"], monkeypatch, price=None)
    out = capsys.readouterr().out
    # With criteria 2/3 evaluable from fundamentals alone, the verdict
    # without a price is WATCH (4 of 7 pass), not INSUFFICIENT_DATA.
    assert "WATCH" in out
