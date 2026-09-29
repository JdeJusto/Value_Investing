"""Tests for the 5-page Streamlit app: page smoke tests + pure helpers.

The page smoke tests run each page standalone with AppTest (empty portfolio,
real reports dir). The helper tests cover the pure functions extracted to
``ui/_shared.py`` and ``backend/services/ui_adapter.py``.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from backend.services.ui_adapter import (
    apply_numeric_filters,
    list_reports,
    parse_daily_report,
    parse_universe_tickers,
)
from ui._shared import format_pct, format_value, normalize_rows, rows_to_csv

PAGES = [
    str(Path(__file__).resolve().parents[2] / page)
    for page in (
        "ui/pages/01_home.py",
        "ui/pages/02_analysis.py",
        "ui/pages/03_screener.py",
        "ui/pages/04_portfolio.py",
        "ui/pages/05_reports.py",
    )
]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page):
    at = AppTest.from_file(page, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def test_format_value_none_is_dash():
    assert format_value(None) == "—"
    assert format_value(3.14159) == "3.14"
    assert format_value(10, unit="$") == "10.00 $"


def test_format_pct_none_is_dash():
    assert format_pct(None) == "—"
    assert format_pct(0.1234) == "12.34%"


def test_rows_to_csv_roundtrip():
    csv_text = rows_to_csv([{"A": 1, "B": "x"}, {"A": 2, "B": "y"}])
    assert csv_text.splitlines() == ["A,B", "1,x", "2,y"]
    assert rows_to_csv([]) == ""


def test_normalize_rows_stringifies_mixed_columns():
    rows = [
        {"Metrica": "a", "Valor": 1.5},
        {"Metrica": "b", "Valor": "HIGH"},
        {"Metrica": "c", "Valor": None},
    ]
    normalized = normalize_rows(rows)
    assert all(isinstance(row["Valor"], str) for row in normalized)
    assert normalized[2]["Valor"] == "—"


def test_normalize_rows_keeps_numeric_columns():
    rows = [{"A": 1.0, "B": "x"}, {"A": None, "B": "y"}]
    normalized = normalize_rows(rows)
    assert normalized[0]["A"] == 1.0
    assert normalized[1]["A"] is None


# ---------------------------------------------------------------------------
# Daily report parsing (Home)
# ---------------------------------------------------------------------------
_REPORT = """# Daily report — 2026-09-29

## Screened
| # | Ticker | Rating | Score | Signal |
|---|---|---|---|---|
| 1 | AAPL | A | 84.0 | WATCHLIST |
| 2 | MSFT | B | 70.0 | BUY_SIGNAL |

## Alerts
- **ABAT** — Trigger event (*MEDIUM*): margen bruto
- **ADAM** — Buy signal (*HIGH*): rank alto
"""


def test_parse_daily_report():
    parsed = parse_daily_report(_REPORT)
    assert parsed["date"] == "2026-09-29"
    assert parsed["screened"][0]["Ticker"] == "AAPL"
    assert parsed["screened"][1]["Score"] == "70.0"
    assert len(parsed["screened"]) == 2
    assert parsed["alerts"][0]["ticker"] == "ABAT"
    assert parsed["alerts"][0]["severity"] == "MEDIUM"
    assert parsed["alerts"][1]["kind"] == "Buy signal"


def test_parse_daily_report_without_sections():
    parsed = parse_daily_report("# Daily report — 2026-01-01\n\nno tables here\n")
    assert parsed["date"] == "2026-01-01"
    assert parsed["screened"] == []
    assert parsed["alerts"] == []


# ---------------------------------------------------------------------------
# Reports listing
# ---------------------------------------------------------------------------
def test_list_reports_orders_newest_first(tmp_path: Path):
    old = tmp_path / "daily_2026-01-01.md"
    new = tmp_path / "daily_2026-02-01.md"
    old.write_text("# old")
    time.sleep(0.01)
    new.write_text("# new")
    entries = list_reports(tmp_path)
    assert [entry["filename"] for entry in entries] == [
        "daily_2026-02-01.md",
        "daily_2026-01-01.md",
    ]
    assert entries[0]["size"] > 0


def test_list_reports_missing_dir(tmp_path: Path):
    assert list_reports(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# Screener helpers
# ---------------------------------------------------------------------------
_UNIVERSE = """ticker,cik,company_name,source_index
AAPL,1,Apple,"SP500,NASDAQ100"
KO,2,Coca-Cola,SP500
ZZZ,3,Small Cap,RUSSELL2000
"""


def test_parse_universe_tickers():
    assert parse_universe_tickers(_UNIVERSE, ["SP500"]) == ["AAPL", "KO"]
    assert parse_universe_tickers(_UNIVERSE, ["NASDAQ100"]) == ["AAPL"]
    assert parse_universe_tickers(_UNIVERSE, ["All"]) == ["AAPL", "KO", "ZZZ"]
    assert parse_universe_tickers(_UNIVERSE, []) == ["AAPL", "KO", "ZZZ"]


def test_apply_numeric_filters():
    rows = [
        {"ticker": "A", "market_cap": 5e9, "per": 10.0, "roe": 0.20, "fcf_yield": 0.05},
        {
            "ticker": "B",
            "market_cap": 100e9,
            "per": 40.0,
            "roe": 0.05,
            "fcf_yield": 0.01,
        },
        {
            "ticker": "C",
            "market_cap": None,
            "per": None,
            "roe": None,
            "fcf_yield": None,
        },
    ]
    assert [r["ticker"] for r in apply_numeric_filters(rows)] == ["A", "B", "C"]
    assert [r["ticker"] for r in apply_numeric_filters(rows, mcap_min=10.0)] == ["B"]
    assert [r["ticker"] for r in apply_numeric_filters(rows, pe_max=20.0)] == ["A"]
    assert [r["ticker"] for r in apply_numeric_filters(rows, roe_min=0.10)] == ["A"]
    assert [r["ticker"] for r in apply_numeric_filters(rows, fcf_min=0.02)] == ["A"]
