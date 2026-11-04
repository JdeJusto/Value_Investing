"""CLI `rank`: single-methodology and combined rankings."""

from __future__ import annotations

import io
import json
import sys
from typing import ClassVar

import pytest

from backend.methodologies.base import Verdict
from backend.services import cli_output
from backend.services.methodology_ranking_service import (
    CombinedRankedTicker,
    RankedTicker,
)
from cli.commands import rank
from cli.main import main


class _TTY(io.StringIO):
    def isatty(self) -> bool:  # pragma: no cover - trivial
        return True


def _ranked(ticker="AAPL", verdict=Verdict.BUY, score=90.0, reason=None):
    return RankedTicker(
        ticker=ticker,
        verdict=verdict,
        score=score,
        family="DEEP_VALUE",
        n_a_reason=reason,
    )


def _combined(ticker="AAPL"):
    return CombinedRankedTicker(
        ticker=ticker,
        per_methodology={"graham": _ranked(ticker), "lynch": _ranked(ticker)},
        combined_score=88.0,
        combined_verdict=Verdict.BUY,
        rationale="BUY in graham AND BUY in lynch",
    )


class _Patches:
    calls: ClassVar[list[tuple]] = []


@pytest.fixture(autouse=True)
def _patch_services(monkeypatch):
    cli_output.reset_no_color()
    _Patches.calls = []
    monkeypatch.setattr(rank, "_resolve_universe", lambda name: ["AAPL", "MSFT"])
    monkeypatch.setattr(
        rank,
        "rank_by_methodology",
        lambda methodology, universe, top_n, include_na=False: (
            _Patches.calls.append(("by", methodology, top_n, include_na))
            or [_ranked("AAPL"), _ranked("MSFT", score=80.0)]
        ),
    )
    monkeypatch.setattr(
        rank,
        "rank_combined",
        lambda methodologies, universe, strategy, top_n: (
            _Patches.calls.append(("combine", methodologies, strategy, top_n))
            or [_combined("AAPL")]
        ),
    )
    yield
    cli_output.reset_no_color()


def _run(*argv):
    sys.argv = ["main.py", *argv]
    main()


def test_rank_by_renders_a_sorted_table(capsys):
    _run("rank", "--by", "graham", "--top", "5")

    out = capsys.readouterr().out
    assert "Ranking · by graham" in out
    assert "AAPL" in out and "BUY" in out
    assert _Patches.calls == [("by", "graham", 5, False)]


def test_rank_combine_passes_strategy(monkeypatch, capsys):
    _run("rank", "--combine", "graham,lynch", "--strategy", "and", "--top", "3")

    out = capsys.readouterr().out
    assert "combine graham,lynch_garp (and)" in out
    assert _Patches.calls == [("combine", ["graham", "lynch_garp"], "and", 3)]


def test_rank_json_is_valid(capsys):
    _run("rank", "--by", "graham", "--json")

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["ticker"] == "AAPL"
    assert payload[0]["verdict"] == "BUY"
    assert payload[0]["score"] == 90.0


def test_rank_combine_json_keeps_per_methodology(capsys):
    _run("rank", "--combine", "graham,lynch", "--json")

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["ticker"] == "AAPL"
    assert payload[0]["per_methodology"]["graham"]["verdict"] == "BUY"


def test_rank_include_na_passes_the_flag(monkeypatch, capsys):
    _run("rank", "--by", "graham", "--include-na")

    assert _Patches.calls[-1] == ("by", "graham", 20, True)
    assert "N/A reason" in capsys.readouterr().out


def test_rank_json_unknown_methodology_exits_two(monkeypatch, capsys):
    def _boom(*args, **kwargs):
        raise ValueError("Unknown methodology: nope")

    monkeypatch.setattr(rank, "rank_by_methodology", _boom)
    with pytest.raises(SystemExit) as excinfo:
        _run("rank", "--by", "nope")

    assert excinfo.value.code == 2
    assert "Unknown methodology" in capsys.readouterr().out


def test_rank_no_color_disables_ansi(monkeypatch):
    out = _TTY()
    monkeypatch.setattr(sys, "stdout", out)
    _run("rank", "--by", "graham", "--no-color")

    assert "\x1b[" not in out.getvalue()
