"""CLI consensus commands: single ticker, ranking and per-category."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cli.commands import consensus as consensus_cmd
from cli.commands import consensus_by_category, consensus_ranking
from cli.commands.consensus_ranking import rank

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "consensus"
    / "consensus_demo.json"
)

METHODOLOGIES = (
    "buffett_classic",
    "buffett_clark",
    "fisher_quantitative_subset",
    "graham",
    "graham_dodd",
    "greenblatt",
    "lynch_garp",
    "marks",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    consensus_cmd.register(sub)
    consensus_ranking.register(sub)
    consensus_by_category.register(sub)
    return parser


def _args(argv: list[str]):
    return _parser().parse_args(argv)


def _write_report(directory: Path, *, universe: str, date: str, tickers=None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["universe"] = universe
    payload["date"] = date
    if tickers is not None:
        payload["companies"] = {
            ticker: payload["companies"][ticker]
            for ticker in tickers
            if ticker in payload["companies"]
        }
    path = directory / f"consensus_{date}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")


# ---------------------------------------------------------------------------
# consensus <ticker> (computed directly, no file)
# ---------------------------------------------------------------------------
VERDICTS = {
    "buffett_classic": "BUY",
    "buffett_clark": "HOLD",
    "fisher_quantitative_subset": "STRONG_BUY",
    "graham": "AVOID",
    "graham_dodd": "AVOID",
    "greenblatt": "INSUFFICIENT_DATA",
    "lynch_garp": "WATCH",
    "marks": "HOLD",
}


@pytest.fixture
def direct(monkeypatch):
    """Mock the direct methodology run (no DB, no network, no file)."""
    from types import SimpleNamespace

    repository = SimpleNamespace(
        get_best_available=lambda ticker: [object()],
        get_company_name=lambda ticker: "Apple Inc.",
    )
    prices = SimpleNamespace(
        get_current_price=lambda ticker: 150.0,
        get_market_cap=lambda ticker: 2e12,
        get_beta=lambda ticker: 1.2,
    )
    view = SimpleNamespace(
        details=[
            {"methodology": name, "verdict": verdict, "flags": []}
            for name, verdict in VERDICTS.items()
        ],
        category="Stalwart",
        category_short="STALWART",
    )
    monkeypatch.setattr(
        "backend.app.cli.build_financial_repository", lambda: repository
    )
    monkeypatch.setattr(
        "backend.services.price_service.get_price_service", lambda: prices
    )
    monkeypatch.setattr(
        "backend.services.ui_adapter.run_methodologies",
        lambda *args, **kwargs: view,
    )
    return view


def test_consensus_prints_all_methodologies_and_the_summary(direct, capsys):
    args = _args(["consensus", "AAPL"])
    consensus_cmd._run(args)
    out = capsys.readouterr().out
    for methodology in METHODOLOGIES:
        assert methodology in out
    assert "As of:" in out
    assert "Universe: single ticker" in out
    assert "Consensus score:" in out
    assert "Lynch category:" in out
    assert "Price at computation:" in out


def test_consensus_single_ticker_needs_no_precomputed_file(monkeypatch, capsys):
    """The command must not read a consensus file at all."""
    monkeypatch.setattr(
        consensus_cmd,
        "load_report",
        lambda args: pytest.fail("consensus must not load a file"),
    )
    from types import SimpleNamespace

    repository = SimpleNamespace(
        get_best_available=lambda ticker: [object()],
        get_company_name=lambda ticker: "Apple Inc.",
    )
    prices = SimpleNamespace(
        get_current_price=lambda ticker: 150.0,
        get_market_cap=lambda ticker: None,
        get_beta=lambda ticker: None,
    )
    view = SimpleNamespace(
        details=[{"methodology": "graham", "verdict": "BUY", "flags": []}],
        category="Stalwart",
        category_short="STALWART",
    )
    monkeypatch.setattr(
        "backend.app.cli.build_financial_repository", lambda: repository
    )
    monkeypatch.setattr(
        "backend.services.price_service.get_price_service", lambda: prices
    )
    monkeypatch.setattr(
        "backend.services.ui_adapter.run_methodologies",
        lambda *args, **kwargs: view,
    )

    consensus_cmd._run(_args(["consensus", "AAPL"]))
    assert "Consensus — AAPL" in capsys.readouterr().out


def test_consensus_ignores_universe_flag(direct, capsys):
    """--universe is accepted for compatibility but never required."""
    consensus_cmd._run(_args(["consensus", "AAPL", "--universe", "nasdaq100"]))
    out = capsys.readouterr().out
    assert "Consensus — AAPL" in out
    assert "single ticker" in out


def test_consensus_unknown_ticker(direct, monkeypatch, capsys):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "backend.app.cli.build_financial_repository",
        lambda: SimpleNamespace(get_best_available=lambda ticker: []),
    )
    consensus_cmd._run(_args(["consensus", "ZZZZ"]))
    out = capsys.readouterr().out
    assert "Unknown ticker or no fundamentals" in out


def test_consensus_csv_export_writes_one_row_per_methodology(direct, tmp_path, capsys):
    csv_path = tmp_path / "aapl.csv"
    consensus_cmd._run(_args(["consensus", "AAPL", "--csv", str(csv_path)]))
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("Ticker,Name,Category,As of,Universe,Methodology")
    assert len(lines) == 1 + len(METHODOLOGIES)


def test_available_consensus_universes_reads_payload(tmp_path):
    _write_report(tmp_path, universe="sp500", date="2026-11-01")
    _write_report(tmp_path, universe="nasdaq100", date="2026-11-02")
    (tmp_path / "consensus_broken.json").write_text("{not json", encoding="utf-8")

    assert consensus_cmd.available_consensus_universes(tmp_path) == [
        "nasdaq100",
        "sp500",
    ]


# ---------------------------------------------------------------------------
# consensus-ranking
# ---------------------------------------------------------------------------
def test_ranking_top_limits_the_rows(demo, capsys):
    args = _args(["consensus-ranking", "--demo", "--top", "5"])
    rows = consensus_ranking._run(args)
    assert len(rows) == 5
    assert [row["Rank"] for row in rows] == ["1", "2", "3", "4", "5"]


def test_ranking_by_avoid_sorts_descending(demo):
    args = _args(["consensus-ranking", "--demo", "--by", "avoid"])
    rows = consensus_ranking._run(args)
    avoids = [int(row["AVOIDs"]) for row in rows]
    assert avoids == sorted(avoids, reverse=True)
    assert rows[0]["Ticker"] == "TSLA"  # 7 AVOIDs in the fixture


def test_ranking_by_score_uses_consensus_score(demo):
    args = _args(["consensus-ranking", "--demo", "--by", "score"])
    rows = consensus_ranking._run(args)
    scores = [int(row["Score"]) for row in rows]
    assert scores == sorted(scores, reverse=True)
    assert rows[0]["Ticker"] == "PLD"  # +5 in the fixture


def test_rank_excludes_all_insufficient_companies():
    import backend.services.consensus_service as service_module

    report = service_module.ConsensusService().load_file(FIXTURE)
    assert report is not None
    tickers = [company.ticker for company in rank(report.companies)]
    assert "JPM" not in tickers  # all-INSUFFICIENT data hole


def test_ranking_csv_export(demo, tmp_path):
    csv_path = tmp_path / "ranking.csv"
    args = _args(["consensus-ranking", "--demo", "--top", "3", "--csv", str(csv_path)])
    consensus_ranking._run(args)
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].split(",")[0] == "Rank"
    assert len(lines) == 4  # header + 3 rows


# ---------------------------------------------------------------------------
# consensus-by-category
# ---------------------------------------------------------------------------
def test_by_category_groups_the_six_buckets(demo, capsys):
    args = _args(["consensus-by-category", "--demo", "--per-category", "5"])
    rows = consensus_by_category._run(args)
    out = capsys.readouterr().out
    for category in (
        "SLOW_GROWER",
        "STALWART",
        "FAST_GROWER",
        "CYCLICAL",
        "TURNAROUND",
        "ASSET_PLAY",
    ):
        assert category in out
    categories = {row["Category"] for row in rows}
    assert "STALWART" in categories
    assert "ASSET_PLAY" in categories


def test_by_category_skips_empty_categories(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("VI_DEMO", raising=False)
    _write_report(
        tmp_path,
        universe="sp500",
        date=datetime.now(UTC).date().isoformat(),
        tickers=["AAPL"],  # Stalwart only
    )
    monkeypatch.setattr(consensus_cmd, "default_consensus_dir", lambda: tmp_path)
    args = _args(["consensus-by-category", "--per-category", "5"])
    rows = consensus_by_category._run(args)
    out = capsys.readouterr().out
    assert "No companies in this category in the current universe." in out
    assert {row["Category"] for row in rows} == {"STALWART"}


# ---------------------------------------------------------------------------
# common flags
# ---------------------------------------------------------------------------
def test_date_flag_filters_to_a_specific_file(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("VI_DEMO", raising=False)
    today = datetime.now(UTC).date()
    older = (today - timedelta(days=1)).isoformat()
    newest = today.isoformat()
    _write_report(tmp_path, universe="sp500", date=older)
    _write_report(tmp_path, universe="sp500", date=newest)
    monkeypatch.setattr(consensus_cmd, "default_consensus_dir", lambda: tmp_path)
    args = _args(["consensus-ranking", "--date", older, "--top", "1"])
    rows = consensus_ranking._run(args)
    out = capsys.readouterr().out
    assert older in out
    assert len(rows) == 1


def test_universe_flag_filters_and_reports_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("VI_DEMO", raising=False)
    _write_report(
        tmp_path, universe="nasdaq100", date=datetime.now(UTC).date().isoformat()
    )
    monkeypatch.setattr(consensus_cmd, "default_consensus_dir", lambda: tmp_path)
    args = _args(["consensus-ranking", "--universe", "nasdaq100", "--top", "1"])
    assert len(consensus_ranking._run(args)) == 1

    args = _args(
        [
            "consensus-ranking",
            "--universe",
            "sp500",
            "--top",
            "1",
            "--no-compute",
        ]
    )
    consensus_ranking._run(args)
    assert "No precomputed consensus for universe sp500" in capsys.readouterr().out


def test_demo_flag_reads_the_bundled_fixture(demo):
    args = _args(["consensus-ranking", "--demo", "--top", "1"])
    report = consensus_cmd.load_report(args)
    assert report is not None
    assert report.universe == "sp500"
    assert len(report.companies) == 30


def test_consensus_renders_the_verdict_table(demo, capsys):
    """The methodology/verdict block is a framed table, still plain when
    stdout is redirected."""
    args = _args(["consensus", "AAPL", "--demo"])
    consensus_cmd._run(args)
    out = capsys.readouterr().out

    assert "┏" in out and "┃" in out and "└" in out
    assert "Methodology" in out and "Verdict" in out
    for methodology in METHODOLOGIES:
        assert methodology in out
    assert "\x1b" not in out


def test_by_category_renders_one_table_per_category(demo, capsys):
    args = _args(["consensus-by-category", "--demo", "--per-category", "3"])
    rows = consensus_by_category._run(args)
    out = capsys.readouterr().out

    assert "┏" in out
    for header in ("#", "Ticker", "Name", "BUYs", "AVOIDs", "Score"):
        assert header in out
    assert rows
    assert "\x1b" not in out


def test_ranking_auto_computes_when_the_file_is_missing(monkeypatch, capsys, tmp_path):
    from backend.services.consensus_service import ConsensusService

    report = ConsensusService().load_file(FIXTURE)
    calls: list[list[str]] = []
    reports = iter([None, report])

    def _compute(argv):
        calls.append(argv)
        output_dir = Path(argv[argv.index("--output-dir") + 1])
        (output_dir / "consensus_2026-11-14.json").write_text(
            json.dumps({"date": "2026-11-14", "universe": "russell2000"}),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(consensus_ranking, "load_report", lambda args: next(reports))
    monkeypatch.setattr(consensus_ranking, "default_consensus_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "scripts.compute_consensus_rankings.main",
        _compute,
    )

    rows = consensus_ranking._run(
        _args(["consensus-ranking", "--universe", "russell2000", "--top", "5"])
    )

    assert calls[0][:2] == ["--universe", "russell2000"]
    assert "--output-dir" in calls[0]
    assert (tmp_path / "consensus_2026-11-14_russell2000.json").exists()
    assert len(rows) == 5
    out = capsys.readouterr().out
    assert "Computing consensus for 'russell2000'" in out
    assert "✓" not in out  # no menu markers from the CLI


def test_ranking_no_compute_fails_fast(monkeypatch, capsys):
    calls: list[list[str]] = []
    monkeypatch.setattr(consensus_ranking, "load_report", lambda args: None)
    monkeypatch.setattr(
        "scripts.compute_consensus_rankings.main",
        lambda argv: calls.append(argv) or 0,
    )

    rows = consensus_ranking._run(
        _args(
            [
                "consensus-ranking",
                "--universe",
                "russell2000",
                "--no-compute",
            ]
        )
    )

    assert rows == []
    assert calls == []
    out = capsys.readouterr().out
    assert "Available:" in out
    assert "vi consensus-ranking --universe russell2000" in out
