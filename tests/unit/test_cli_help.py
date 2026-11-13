"""`vi help` alias, catalog search and unknown-command suggestions."""

from __future__ import annotations

import sys

import pytest

from cli.command_catalog import CATALOG
from cli.main import main


def _run(monkeypatch, *argv: str):
    monkeypatch.setattr(sys, "argv", ["main.py", *argv])
    return main()


def test_help_without_arguments_prints_the_grouped_help(monkeypatch, capsys):
    _run(monkeypatch, "help")

    out = capsys.readouterr().out
    assert "usage:" in out
    assert "Common tasks:" in out


def test_help_alias_shows_a_command_help(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exit_info:
        _run(monkeypatch, "help", "rank")

    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert "usage: main.py rank" in out
    assert "vi rank --by graham --top 20" in out


def test_help_search_finds_rank_and_methodologies(monkeypatch, capsys):
    _run(monkeypatch, "help", "--search", "methodology")

    out = capsys.readouterr().out
    assert "Top matches for 'methodology'" in out
    assert "vi rank" in out
    assert "vi methodologies" in out


def test_help_search_without_matches(monkeypatch, capsys):
    _run(monkeypatch, "help", "--search", "zzzzz")

    out = capsys.readouterr().out
    assert "No commands match 'zzzzz'" in out


def test_unknown_command_suggests_rank(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exit_info:
        _run(monkeypatch, "top")

    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert "Unknown command 'top'" in err
    assert "Did you mean 'vi rank'?" in err


def test_catalog_covers_every_top_level_command():
    assert len(CATALOG) == 44
    assert {
        "rank",
        "scorecard",
        "financials",
        "dcf",
        "backtest",
        "refresh",
        "screener",
        "consensus",
    } <= set(CATALOG)
