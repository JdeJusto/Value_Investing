"""Consensus page: renders in demo mode with all four lenses."""

from __future__ import annotations

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


@pytest.fixture(autouse=True)
def _demo(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")


def _run() -> AppTest:
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def test_page_renders_with_the_demo_fixture():
    at = _run()
    assert not any("No consensus data available" in info.value for info in at.info)
    assert any(subheader.value == "Top by consensus" for subheader in at.subheader)
    assert any(select.label == "Universe" for select in at.selectbox)


def test_top_by_consensus_table_is_present():
    at = _run()
    frames = [frame.value for frame in at.dataframe]
    assert any(
        {"Ticker", "Category", "BUYs", "AVOIDs", "Score", "Verdicts"}
        <= set(frame.columns)
        for frame in frames
    )


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
