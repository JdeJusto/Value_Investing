"""Consensus page: renders in demo mode with all four lenses."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "06_consensus.py"

LYNCH_SIX = (
    "SLOW_GROWER",
    "STALWART",
    "FAST_GROWER",
    "CYCLICAL",
    "TURNAROUND",
    "ASSET_PLAY",
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


def _write_report(directory: Path, companies: dict[str, dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    date = datetime.now(UTC).date().isoformat()
    payload = {
        "version": 2,
        "date": date,
        "universe": "sp500",
        "prices_available": False,
        "prices_snapshot": {},
        "companies": companies,
    }
    (directory / f"consensus_{date}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _company(name: str, verdicts: list[str], category: str) -> dict:
    counts = {verdict: verdicts.count(verdict) for verdict in set(verdicts)}
    return {
        "name": name,
        "verdicts": dict(zip(METHODOLOGIES, verdicts, strict=True)),
        "buy_count": counts.get("BUY", 0),
        "avoid_count": counts.get("AVOID", 0),
        "insufficient_count": counts.get("INSUFFICIENT_DATA", 0),
        "consensus_score": counts.get("BUY", 0) - counts.get("AVOID", 0),
        "lynch_category": category,
        "price": None,
        "prices_available": False,
    }


@pytest.fixture(autouse=True)
def _demo(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")


def _run() -> AppTest:
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def _top_frame(at: AppTest):
    frames = [frame.value for frame in at.dataframe]
    return next(frame for frame in frames if "Verdicts" in frame.columns)


def _sorted_tickers(monkeypatch, tmp_path) -> AppTest:
    monkeypatch.setattr(
        "backend.services.consensus_service.default_consensus_dir", lambda: tmp_path
    )
    _write_report(
        tmp_path,
        {
            # More BUYs but heavily rejected: score -2.
            "BIGAVOID": _company(
                "Big Avoid Inc.",
                ["BUY", "BUY", "BUY", "AVOID", "AVOID", "AVOID", "AVOID", "AVOID"],
                "CYCLICAL",
            ),
            # Fewer BUYs but nobody rejects it: score +2.
            "STEADY": _company(
                "Steady Inc.",
                ["BUY", "BUY", "WATCH", "HOLD", "WATCH", "HOLD", "WATCH", "HOLD"],
                "STALWART",
            ),
        },
    )
    return _run()


def test_page_renders_with_the_demo_fixture():
    at = _run()
    assert not any("No consensus data available" in info.value for info in at.info)
    assert any(subheader.value == "Top by consensus" for subheader in at.subheader)
    assert any(select.label == "Universe" for select in at.selectbox)


def test_top_by_consensus_table_is_present():
    at = _run()
    frame = _top_frame(at)
    assert {
        "Ticker",
        "Category",
        "BUYs",
        "AVOIDs",
        "Consensus score",
        "Verdicts",
    } <= set(frame.columns)


def test_default_sort_is_by_consensus_score(monkeypatch, tmp_path):
    at = _sorted_tickers(monkeypatch, tmp_path)
    sort = next(radio for radio in at.radio if radio.label == "Sort by")
    assert sort.value == "Consensus score"
    assert list(_top_frame(at)["Ticker"]) == ["STEADY", "BIGAVOID"]


def test_switching_to_buys_resorts_the_table(monkeypatch, tmp_path):
    at = _sorted_tickers(monkeypatch, tmp_path)
    next(radio for radio in at.radio if radio.label == "Sort by").set_value("BUYs")
    at.run()
    assert not at.exception, at.exception
    assert list(_top_frame(at)["Ticker"]) == ["BIGAVOID", "STEADY"]


def test_switching_to_avoids_resorts_the_table(monkeypatch, tmp_path):
    at = _sorted_tickers(monkeypatch, tmp_path)
    next(radio for radio in at.radio if radio.label == "Sort by").set_value("AVOIDs")
    at.run()
    assert not at.exception, at.exception
    assert list(_top_frame(at)["Ticker"]) == ["BIGAVOID", "STEADY"]


def test_lynch_category_expander_shows_six_blocks():
    at = _run()
    labels = [markdown.value for markdown in at.markdown]
    for category in LYNCH_SIX:
        assert f"**{category}**" in labels
    assert any(expander.label == "Best per Lynch category" for expander in at.expander)


def test_disagreement_zone_expander_exists():
    at = _run()
    labels = [expander.label for expander in at.expander]
    assert any("Disagreement zone" in label for label in labels)


def test_verdict_matrix_expander_exposes_every_methodology():
    at = _run()
    frames = [frame.value for frame in at.dataframe]
    matrix = next(
        (frame for frame in frames if "buffett_classic" in frame.columns), None
    )
    assert matrix is not None, [list(frame.columns) for frame in frames]
    assert {"buffett_clark", "graham", "greenblatt", "lynch_garp", "marks"} <= set(
        matrix.columns
    )


def test_missing_data_shows_the_generation_hint(monkeypatch, tmp_path):
    monkeypatch.delenv("VI_DEMO", raising=False)
    monkeypatch.setattr(
        "backend.services.consensus_service.default_consensus_dir", lambda: tmp_path
    )
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert any("No consensus data available" in info.value for info in at.info)
