"""Portfolio thesis CLI (set/show/clear/set-from-file) and persistence."""

from __future__ import annotations

import argparse
from argparse import Namespace

from backend.portfolio.portfolio_repository import JsonPortfolioRepository
from backend.portfolio.portfolio_service import PortfolioService
from cli.commands import portfolio as portfolio_cli


def _service(tmp_path) -> PortfolioService:
    return PortfolioService(JsonPortfolioRepository(tmp_path / "portfolio.json"))


def _seed(service: PortfolioService, ticker: str = "AAPL") -> None:
    service.add(ticker, 10, 100.0)


def _patch_service(monkeypatch, service: PortfolioService) -> None:
    monkeypatch.setattr(portfolio_cli, "build_portfolio_service", lambda: service)


def test_thesis_subcommand_is_registered():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    portfolio_cli.register(sub)

    args = parser.parse_args(["portfolio", "thesis", "AAPL", "--set", "Moat"])

    assert args.action == "thesis"
    assert args.ticker == "AAPL"
    assert args.set_text == "Moat"
    assert args.func is portfolio_cli._thesis


def test_thesis_set_and_show(monkeypatch, capsys, tmp_path):
    service = _service(tmp_path)
    _seed(service)
    _patch_service(monkeypatch, service)

    portfolio_cli._thesis(
        Namespace(
            ticker="AAPL",
            set_text="Brand and pricing power",
            set_from_file=None,
            clear=False,
        )
    )
    assert service.get("AAPL").thesis == "Brand and pricing power"

    capsys.readouterr()
    portfolio_cli._thesis(
        Namespace(ticker="AAPL", set_text=None, set_from_file=None, clear=False)
    )
    out = capsys.readouterr().out
    assert "AAPL:" in out
    assert "Brand and pricing power" in out


def test_thesis_clear(monkeypatch, capsys, tmp_path):
    service = _service(tmp_path)
    _seed(service)
    service.set_thesis("AAPL", "Old thesis")
    _patch_service(monkeypatch, service)

    portfolio_cli._thesis(
        Namespace(ticker="AAPL", set_text=None, set_from_file=None, clear=True)
    )

    assert service.get("AAPL").thesis is None
    assert "Thesis cleared for AAPL" in capsys.readouterr().out


def test_thesis_set_from_file(monkeypatch, capsys, tmp_path):
    service = _service(tmp_path)
    _seed(service)
    _patch_service(monkeypatch, service)
    thesis_file = tmp_path / "thesis.md"
    thesis_file.write_text("Long thesis.\n", encoding="utf-8")

    portfolio_cli._thesis(
        Namespace(
            ticker="AAPL",
            set_text=None,
            set_from_file=str(thesis_file),
            clear=False,
        )
    )

    assert service.get("AAPL").thesis == "Long thesis."
    assert "Thesis saved for AAPL" in capsys.readouterr().out


def test_thesis_persists_across_loads(tmp_path):
    service = _service(tmp_path)
    _seed(service)
    service.set_thesis("AAPL", "Persisted")

    reloaded = JsonPortfolioRepository(tmp_path / "portfolio.json").load()
    assert reloaded.position("AAPL").thesis == "Persisted"


def test_thesis_missing_position(monkeypatch, capsys, tmp_path):
    service = _service(tmp_path)
    _patch_service(monkeypatch, service)

    portfolio_cli._thesis(
        Namespace(ticker="AAPL", set_text="x", set_from_file=None, clear=False)
    )

    assert "No open position for" in capsys.readouterr().out


def test_thesis_line_truncates_long_text():
    line = portfolio_cli._thesis_line("AAPL", "x" * 80)
    text = str(line)
    assert "..." in text
    assert "x" * 80 not in text
