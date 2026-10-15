"""CLI `scorecard`: registration, rendering, --json output and exit codes."""

from __future__ import annotations

import io
import json
import sys
from typing import ClassVar

import pytest

from backend.services import cli_output
from backend.services.scorecard_service import (
    DIMENSION_ORDER,
    DimensionRule,
    DimensionScore,
    Scorecard,
)
from cli.main import main

_LABELS = {
    "growth": "Growth",
    "profitability": "Profitability",
    "financial_health": "Financial Health",
    "valuation": "Valuation",
    "shareholder_returns": "Shareholder Returns",
    "management_moat": "Management/Moat",
}


def _card(
    ticker: str = "AAPL", overall: str = "Mixed", peers: bool = False
) -> Scorecard:
    dimensions = tuple(
        DimensionScore(
            key=key,
            label=_LABELS[key],
            question="q",
            score=7,
            verdict="Mixed",
            confidence="HIGH",
            evaluable_rules=5,
            rules=(
                DimensionRule(
                    rule_id=f"{key}_rule",
                    label="Revenue CAGR (5y)",
                    status="PASS",
                    value="12.4%",
                    threshold="≥ 10%",
                    reason="r",
                    peer_median="15.50x" if peers else None,
                    peer_percentile=0.62 if peers else None,
                ),
            ),
            trend="improving",
            summary="7/10 — Mixed (5 rules).",
            peer_group="Consumer Electronics" if peers else None,
            peer_group_level="industry" if peers else None,
            peer_group_size=14 if peers else None,
        )
        for key in DIMENSION_ORDER
    )
    return Scorecard(
        ticker=ticker,
        company="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        period="FY",
        price=240.0,
        market_cap=3.6e12,
        generated="",
        dimensions=dimensions,
        overall=overall,
        disagreements=(),
        methodologies=(),
        data_quality="HIGH",
        notes=(),
    )


class _FakeService:
    """Stand-in for ``ScorecardService``: returns a canned card, records calls."""

    card: ClassVar[Scorecard | None] = None
    calls: ClassVar[list[tuple]] = []

    def __init__(self, repository, price_service=None):
        self._repository = repository

    def build(self, ticker, period="FY"):
        type(self).calls.append((ticker, period))
        return type(self).card


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    import backend.app.cli as app_cli
    import backend.services.price_service as price_module
    import backend.services.scorecard_service as scorecard_module

    _FakeService.card = _card()
    _FakeService.calls = []
    cli_output.reset_no_color()
    monkeypatch.delenv("NO_COLOR", raising=False)
    # The fake service ignores its collaborators, but the command still builds
    # them: keep the DB and Yahoo out of the test.
    monkeypatch.setattr(app_cli, "build_financial_repository", lambda: object())
    monkeypatch.setattr(price_module, "get_price_service", lambda: object())
    monkeypatch.setattr(scorecard_module, "ScorecardService", _FakeService)
    yield
    cli_output.reset_no_color()


def _run(*argv):
    sys.argv = ["main.py", *argv]
    main()


class _TTY(io.StringIO):
    def isatty(self) -> bool:  # pragma: no cover - trivial
        return True


def test_command_is_registered_in_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        _run("--help")
    assert excinfo.value.code == 0
    assert "scorecard" in capsys.readouterr().out


def test_json_output_matches_the_service(capsys):
    _run("scorecard", "AAPL", "--json")
    payload = json.loads(capsys.readouterr().out)
    # The command prints the service payload (tuples serialize as arrays).
    expected = json.loads(json.dumps(_FakeService.card.to_dict()))
    assert payload == expected
    assert payload["ticker"] == "AAPL"
    assert [dim["key"] for dim in payload["dimensions"]] == list(DIMENSION_ORDER)
    assert _FakeService.calls == [("AAPL", "FY")]


def test_period_and_ticker_reach_the_service(capsys):
    _run("scorecard", "aapl", "--period", "Q1", "--json")
    assert _FakeService.calls == [("AAPL", "Q1")]


def test_default_rendering_shows_dimensions_scores_and_verdicts(capsys):
    _run("scorecard", "AAPL")
    out = capsys.readouterr().out
    for label in _LABELS.values():
        assert label in out
    assert "7/10" in out
    assert "Mixed" in out
    assert "AAPL" in out
    assert "HIGH" in out  # per-dimension confidence, distinct from data quality
    assert "Confidence" in out
    assert "Data: Financial-DataBase · FY · Prices not persisted." in out


def test_unknown_ticker_exits_two(capsys):
    _FakeService.card = None
    with pytest.raises(SystemExit) as excinfo:
        _run("scorecard", "ZZZZ")
    assert excinfo.value.code == 2
    assert "Unknown ticker: ZZZZ" in capsys.readouterr().out


def test_service_error_exits_three(monkeypatch, capsys):
    import backend.services.scorecard_service as scorecard_module

    class _Boom(_FakeService):
        def build(self, ticker, period="FY"):
            raise RuntimeError("db down")

    monkeypatch.setattr(scorecard_module, "ScorecardService", _Boom)
    with pytest.raises(SystemExit) as excinfo:
        _run("scorecard", "AAPL")
    assert excinfo.value.code == 3
    assert "Could not build the scorecard for AAPL" in capsys.readouterr().out


def test_renders_color_on_a_terminal(monkeypatch):
    out = _TTY()
    monkeypatch.setattr(sys, "stdout", out)
    _run("scorecard", "AAPL")
    assert "\x1b" in out.getvalue()


def test_no_color_flag_strips_ansi(monkeypatch):
    out = _TTY()
    monkeypatch.setattr(sys, "stdout", out)
    _run("scorecard", "AAPL", "--no-color")
    assert "\x1b" not in out.getvalue()


def test_no_color_env_strips_ansi(monkeypatch):
    out = _TTY()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setenv("NO_COLOR", "1")
    _run("scorecard", "AAPL")
    assert "\x1b" not in out.getvalue()


def test_peer_group_line_says_not_available_without_an_artifact(capsys):
    _run("scorecard", "AAPL")
    out = capsys.readouterr().out
    assert "Peer group: not available (run scripts/build_peer_stats.py)" in out
    assert "vs peers" not in out


def test_peer_group_line_and_rule_percentile_are_rendered(capsys):
    _FakeService.card = _card(peers=True)
    _run("scorecard", "AAPL")
    out = capsys.readouterr().out
    assert "Peer group: Consumer Electronics (14 companies, industry)" in out
    assert "vs peers 15.50x · p62" in out


def test_json_payload_carries_the_peer_fields(capsys):
    _FakeService.card = _card(peers=True)
    _run("scorecard", "AAPL", "--json")
    payload = json.loads(capsys.readouterr().out)
    dimension = payload["dimensions"][0]
    assert dimension["peer_group"] == "Consumer Electronics"
    assert dimension["peer_group_size"] == 14
    rule = dimension["rules"][0]
    assert rule["peer_median"] == "15.50x"
    assert rule["peer_percentile"] == pytest.approx(0.62)
