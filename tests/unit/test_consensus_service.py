"""ConsensusService: loading, staleness and the four ranking lenses."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from backend.services.consensus_service import (
    LYNCH_CATEGORIES,
    ConsensusService,
)
from scripts.compute_consensus_rankings import build_company_consensus

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "consensus"
    / "consensus_demo.json"
)


def _write_report(tmp_path: Path, *, stale_days: int = 0) -> Path:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    report_date = datetime.now(UTC).date() - timedelta(days=stale_days)
    payload["date"] = report_date.isoformat()
    path = tmp_path / f"consensus_{payload['date']}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _loaded(tmp_path: Path) -> ConsensusService:
    _write_report(tmp_path)
    service = ConsensusService(directory=tmp_path)
    assert service.load_latest() is not None
    return service


def test_load_latest_reads_the_fixture(tmp_path):
    service = _loaded(tmp_path)
    report = service._report
    assert report is not None
    assert report.universe == "sp500"
    assert len(report.companies) == 9
    aapl = next(c for c in report.companies if c.ticker == "AAPL")
    assert aapl.buy_count == 5
    assert aapl.consensus_score == 4
    assert aapl.verdicts["lynch_garp"] == "BUY"


def test_load_by_date_reads_the_exact_file(tmp_path):
    path = _write_report(tmp_path)
    report = ConsensusService(directory=tmp_path).load_by_date(
        path.stem.removeprefix("consensus_")
    )
    assert report is not None
    assert report.date in path.name
    assert len(report.companies) == 9


def test_missing_file_returns_none_with_a_warning(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        report = ConsensusService(directory=tmp_path).load_latest()
    assert report is None
    assert "no consensus file" in caplog.text


def test_stale_file_returns_none_with_a_warning(tmp_path, caplog):
    _write_report(tmp_path, stale_days=60)
    service = ConsensusService(directory=tmp_path)
    with caplog.at_level(logging.WARNING):
        report = service.load_latest()
    assert report is None
    assert "stale" in caplog.text
    assert service.top_by_consensus(5) == []


def test_top_by_consensus_orders_by_buys_then_score(tmp_path):
    service = _loaded(tmp_path)
    tickers = [c.ticker for c in service.top_by_consensus(10)]
    assert tickers == ["PLD", "AAPL", "MSFT", "XOM", "JNJ", "KO", "COLD", "TSLA"]


def test_all_insufficient_companies_are_excluded(tmp_path):
    service = _loaded(tmp_path)
    ranked = service.top_by_consensus(10)
    assert all(c.ticker != "JPM" for c in ranked)
    assert all(not c.is_data_hole for c in ranked)


def test_best_per_lynch_category_groups_all_six_buckets(tmp_path):
    service = _loaded(tmp_path)
    grouped = service.best_per_lynch_category(5)
    assert set(LYNCH_CATEGORIES) <= set(grouped)
    assert [c.ticker for c in grouped["ASSET_PLAY"]] == ["PLD"]
    stalwarts = [c.ticker for c in grouped["STALWART"]]
    assert stalwarts == ["AAPL", "JNJ"]
    assert [c.ticker for c in grouped["CYCLICAL"]] == ["XOM"]


def test_disagreement_zone_requires_both_camps(tmp_path):
    service = _loaded(tmp_path)
    tickers = [c.ticker for c in service.disagreement_zone(3, 5)]
    assert tickers == ["XOM", "JNJ"]


def test_verdict_matrix_has_one_column_per_methodology(tmp_path):
    service = _loaded(tmp_path)
    rows = service.verdict_matrix()
    assert rows
    assert set(rows[0]) == {
        "Ticker",
        "Name",
        "buffett_classic",
        "buffett_clark",
        "fisher_quantitative_subset",
        "graham",
        "graham_dodd",
        "greenblatt",
        "lynch_garp",
        "marks",
    }


def test_build_company_consensus_aggregates_a_view():
    view = SimpleNamespace(
        details=[
            {"methodology": name, "verdict": verdict}
            for name, verdict in (
                ("buffett_classic", "BUY"),
                ("buffett_clark", "AVOID"),
                ("fisher_quantitative_subset", "BUY"),
                ("graham", "AVOID"),
                ("graham_dodd", "BUY"),
                ("greenblatt", "HOLD"),
                ("lynch_garp", "BUY"),
                ("marks", "WATCH"),
            )
        ]
    )

    row = build_company_consensus("ABC", "ABC Corp", view)
    assert row["buy_count"] == 4
    assert row["avoid_count"] == 2
    assert row["insufficient_count"] == 0
    assert row["consensus_score"] == 2
    assert row["lynch_category"] == "UNKNOWN"  # no category detail in the view


def test_build_company_consensus_reads_the_lynch_category():
    view = SimpleNamespace(
        details=[
            {"methodology": "lynch_garp", "verdict": "BUY", "category": "STALWART"}
        ]
    )

    row = build_company_consensus("ABC", "ABC Corp", view)
    assert row["lynch_category"] == "STALWART"
    assert row["verdicts"]["marks"] == "INSUFFICIENT_DATA"  # schema completed
