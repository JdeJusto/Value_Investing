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
# consensus <ticker>
# ---------------------------------------------------------------------------
def test_consensus_prints_all_methodologies_and_the_summary(demo, capsys):
    args = _args(["consensus", "AAPL", "--demo"])
    consensus_cmd._run(args)
    out = capsys.readouterr().out
    for methodology in METHODOLOGIES:
        assert methodology in out
    assert "As of:" in out
    assert "Consensus score:" in out
    assert "Lynch category:" in out
    assert "Price at computation:" in out


def test_consensus_unknown_ticker_prints_the_run_hint(demo, capsys):
    args = _args(["consensus", "ZZZZ", "--demo"])
    consensus_cmd._run(args)
    out = capsys.readouterr().out
    assert "Ticker ZZZZ not found in the latest consensus" in out
    assert "compute_consensus_rankings" in out


def test_consensus_missing_file_prints_the_run_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("VI_DEMO", raising=False)
    monkeypatch.setattr(consensus_cmd, "default_consensus_dir", lambda: tmp_path)
    args = _args(["consensus", "AAPL"])
    consensus_cmd._run(args)
    out = capsys.readouterr().out
    assert "No consensus file found" in out
    assert "compute_consensus_rankings" in out


def test_consensus_csv_export_writes_one_row_per_methodology(demo, tmp_path, capsys):
    csv_path = tmp_path / "aapl.csv"
    args = _args(["consensus", "AAPL", "--demo", "--csv", str(csv_path)])
    consensus_cmd._run(args)
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("Ticker,Name,Category,As of,Universe,Methodology")
    assert len(lines) == 1 + len(METHODOLOGIES)


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

    args = _args(["consensus-ranking", "--universe", "sp500", "--top", "1"])
    consensus_ranking._run(args)
    assert "No consensus file found" in capsys.readouterr().out


def test_demo_flag_reads_the_bundled_fixture(demo):
    args = _args(["consensus-ranking", "--demo", "--top", "1"])
    report = consensus_cmd.load_report(args)
    assert report is not None
    assert report.universe == "sp500"
    assert len(report.companies) == 30
