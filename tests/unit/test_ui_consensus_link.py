"""Analysis page: the inline consensus entry expander."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "02_analysis.py"

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


def _run(monkeypatch) -> AppTest:
    monkeypatch.setenv("VI_DEMO", "1")
    at = AppTest.from_file(str(PAGE), default_timeout=180)
    at.run()
    next(button for button in at.button if button.label == "Analyze").click()
    at.run()
    assert not at.exception, at.exception
    return at


def _write_report(directory: Path, tickers: list[str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "date": datetime.now(UTC).date().isoformat(),
        "universe": "sp500",
        "prices_available": bool(tickers),
        "prices_snapshot": {ticker: 100.0 for ticker in tickers},
        "companies": {
            ticker: {
                "name": f"{ticker} Inc.",
                "verdicts": {name: "BUY" for name in METHODOLOGIES},
                "buy_count": 8,
                "avoid_count": 0,
                "insufficient_count": 0,
                "consensus_score": 8,
                "lynch_category": "STALWART",
                "price": 100.0,
                "prices_available": True,
            }
            for ticker in tickers
        },
    }
    (directory / f"consensus_{payload['date']}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_demo_consensus_expander_shows_metrics_and_verdicts(monkeypatch):
    at = _run(monkeypatch)
    assert any(expander.label == "Consensus entry" for expander in at.expander)
    labels = [metric.label for metric in at.metric]
    assert {"BUYs", "AVOIDs", "Score", "Category"} <= set(labels)
    tables = [frame.value for frame in at.dataframe]
    assert any(list(frame.columns) == ["Methodology", "Verdict"] for frame in tables)
    assert any("Price at computation" in caption.value for caption in at.caption)


def test_ticker_missing_from_consensus_shows_a_warning(monkeypatch, tmp_path):
    _write_report(tmp_path, ["KO"])
    monkeypatch.setattr(
        "backend.services.consensus_service.default_consensus_dir",
        lambda: tmp_path,
    )
    at = _run(monkeypatch)
    assert any("not in the latest consensus" in warning.value for warning in at.warning)


def test_no_consensus_file_shows_the_generation_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.services.consensus_service.default_consensus_dir",
        lambda: tmp_path,
    )
    at = _run(monkeypatch)
    assert any("No consensus report available" in info.value for info in at.info)
    assert any("compute_consensus_rankings" in info.value for info in at.info)
