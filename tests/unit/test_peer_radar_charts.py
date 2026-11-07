"""Peers tab: radar traces and the dimension matrix."""

from __future__ import annotations

from pathlib import Path

from ui.charts import PEER_DIMENSIONS, peer_dimension_rows, peer_radar_figure

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "02_analysis.py"


def _payload() -> dict[str, dict[str, int | None]]:
    return {
        "AAPL": {
            "growth": 7,
            "profitability": 9,
            "financial_health": 7,
            "valuation": 2,
            "shareholder_returns": 8,
            "management_moat": 7,
        },
        "MSFT": {
            "growth": 8,
            "profitability": 9,
            "financial_health": 8,
            "valuation": 3,
            "shareholder_returns": 8,
            "management_moat": 6,
        },
        "NVDA": {
            "growth": 10,
            "profitability": None,
            "financial_health": 9,
            "valuation": 1,
            "shareholder_returns": 6,
            "management_moat": 8,
        },
    }


def test_peer_radar_has_one_trace_per_company_with_the_subject_first():
    figure = peer_radar_figure(_payload())

    assert figure is not None
    assert [trace.name for trace in figure.data] == ["AAPL", "MSFT", "NVDA"]
    assert figure.data[0].line.width == 2
    assert figure.layout.polar.radialaxis.range == (0, 10)


def test_missing_scores_are_gaps_not_zero():
    figure = peer_radar_figure(_payload())

    nvda = figure.data[2]
    assert nvda.r[1] is None


def test_dimension_matrix_rows_and_dashes():
    rows = peer_dimension_rows(_payload())

    assert [row["Dimension"] for row in rows] == [
        label for _key, label in PEER_DIMENSIONS
    ]
    assert list(rows[0]) == ["Dimension", "AAPL", "MSFT", "NVDA"]
    assert rows[0]["AAPL"] == "7/10"
    assert rows[1]["NVDA"] == "—"


def test_analysis_page_registers_the_peers_tab():
    assert '"Peers"' in PAGE.read_text(encoding="utf-8")
