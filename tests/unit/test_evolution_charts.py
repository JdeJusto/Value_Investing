"""Evolution tab helpers: eight 10-year charts."""

from __future__ import annotations

from pathlib import Path

from ui.charts import EVOLUTION_FIELDS, evolution_figures, evolution_has_history

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "02_analysis.py"


def _series(value: float | None = 1_000_000_000.0):
    return [(year, value) for year in range(2016, 2026)]


def test_evolution_figures_have_eight_titles():
    data = {field: _series() for field, _label in EVOLUTION_FIELDS}

    figures = evolution_figures(data)

    assert len(figures) == 8
    assert [figure.layout.title.text for figure in figures] == [
        label for _field, label in EVOLUTION_FIELDS
    ]
    assert figures[0].data[0].y[0] == 1.0


def test_evolution_insufficient_history_when_all_none():
    data = {field: _series(None) for field, _label in EVOLUTION_FIELDS}

    assert evolution_has_history(data) is False
    data["revenue"] = _series()
    assert evolution_has_history(data) is True


def test_analysis_page_registers_evolution_tab():
    assert '"Evolution"' in PAGE.read_text(encoding="utf-8")
