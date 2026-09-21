"""Unit tests for the daily report service and daily workflow helpers."""

from datetime import date

import pytest

from backend.services.daily_report_service import (
    DailyReport,
    build_markdown,
    load_state,
    save_state,
    trim_state,
)


def _analysis(ticker="AAPL", total=78.0, confidence="MEDIUM", margin_delta=None):
    d = {
        "ticker": ticker,
        "composite_score": {
            "total_score": total,
            "rating": "B",
            "confidence": confidence,
        },
        "buffett_score": 82.0,
        "buffett_breakdown": {
            "cash_generation": 80.0,
            "profitability": 85.0,
            "stability": 88.0,
        },
        "moat_analysis": {"moat_type": "MODERATE", "moat_score": 0.7},
        "dcf_margin_of_safety": 0.1,
        "delta_metrics": {},
        "quality_metrics": {"roic_mean": 0.19},
    }
    if margin_delta is not None:
        d["delta_metrics"]["gross_margin_delta"] = margin_delta
    return d


class TestStatePersistence:
    def test_load_state_missing_returns_empty(self, tmp_path):
        assert load_state(str(tmp_path / "nope.json")) == {}

    def test_load_state_corrupt_returns_empty(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("not json", encoding="utf-8")
        assert load_state(str(path)) == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "state.json"
        save_state(str(path), {"AAPL": {"composite_score": {"total_score": 78.0}}})
        assert load_state(str(path)) == {"AAPL": {"composite_score": {"total_score": 78.0}}}

    def test_trim_state_keeps_only_composite(self):
        analyses = {
            "AAPL": {
                "composite_score": {"total_score": 78.0, "rating": "B"},
                "roe": 0.2,
            },
            "MSFT": {"partial": True},
        }
        trimmed = trim_state(analyses)
        assert list(trimmed) == ["AAPL"]
        assert "roe" not in trimmed["AAPL"]
        assert trimmed["AAPL"]["composite_score"]["total_score"] == 78.0


class TestMarkdown:
    def _report(self):
        return DailyReport(
            report_date=date(2026, 9, 13),
            universe_size=2,
            screened_count=1,
            sec_update="SEC update: ok",
            rows=[
                {
                    "rank": 1,
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "rating": "B",
                    "total_score": 78.0,
                    "rank_score": 72.5,
                    "price": 200.0,
                    "per": 15.0,
                    "fcf_yield": 0.08,
                    "ev_ebit": 12.0,
                    "signal": "BUY",
                }
            ],
            alerts=[
                {
                    "ticker": "AAPL",
                    "alert_type": "BUY_SIGNAL",
                    "reason": ["rank 78 with composite above 70"],
                    "confidence": "MEDIUM",
                }
            ],
            missing=["XDATA"],
            price_notes=["real-time price unavailable for: XDATA"],
            runtime_seconds=12.3,
        )

    def test_build_markdown_contains_sections(self):
        md = build_markdown(self._report())
        assert "# Daily report — 2026-09-13" in md
        assert "SEC update: ok" in md
        assert "| # | Ticker |" in md
        assert "| 1 | AAPL | Apple Inc. | B | 78.0 | 72.5 | 200.0 | 15.0 | 8.0% | 12.0 | BUY |" in md
        assert "coverage: **50%**" in md
        assert "Runtime: **12s**" in md
        assert "no price is ever persisted" in md
        assert "`prices` table is untouched" in md
        assert "**AAPL** — Buy signal" in md
        assert "## Missing data" in md
        assert "XDATA" in md

    def test_build_markdown_empty_report(self):
        md = build_markdown(DailyReport(report_date=date(2026, 9, 13)))
        assert "# Daily report — 2026-09-13" in md
        assert "## Screened" not in md


def _current_buy():
    d = _analysis(total=80.0, margin_delta=0.05)
    d["dcf_margin_of_safety"] = 0.4
    d["delta_metrics"]["revenue_growth_delta"] = 0.03
    d["delta_metrics"]["roic_delta"] = 0.04
    return d


class TestAlertFlow:
    def test_run_detects_buy_and_trigger(self):
        from scripts.daily_workflow import run_alerts

        analyses = {"AAPL": _current_buy()}
        alerts = run_alerts(analyses, {})
        types = {a.alert_type for a in alerts}
        assert "TRIGGER_EVENT" in types
        assert "BUY_SIGNAL" in types
        assert all(a.ticker == "AAPL" for a in alerts)

    def test_run_detects_sell_warning_against_previous(self):
        from scripts.daily_workflow import run_alerts

        previous = {"AAPL": {"composite_score": {"total_score": 85.0}}}
        current = _analysis(total=65.0, margin_delta=None)
        alerts = run_alerts({"AAPL": current}, previous)
        types = {a.alert_type for a in alerts}
        assert "SELL_WARNING" in types
        sell = next(a for a in alerts if a.alert_type == "SELL_WARNING")
        assert sell.confidence == "HIGH"

    def test_run_dedupes_per_type(self):
        from scripts.daily_workflow import run_alerts

        analyses = {"AAPL": _current_buy()}
        alerts = run_alerts(analyses, {})
        keys = {(a.ticker, a.alert_type) for a in alerts}
        assert len(keys) == len(alerts)


class TestWorkflowHelpers:
    def test_load_universe_ignores_comments(self, tmp_path):
        from scripts import daily_workflow

        f = tmp_path / "universe.txt"
        f.write_text("# comment\nAAPL\n\nMSFT\n", encoding="utf-8")
        assert daily_workflow._load_universe(str(f)) == ["AAPL", "MSFT"]

    def test_load_universe_empty_raises(self, tmp_path):
        from scripts import daily_workflow

        f = tmp_path / "universe.txt"
        f.write_text("# only comment\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            daily_workflow._load_universe(str(f))

    def test_row_of_includes_metrics(self):
        from scripts import daily_workflow

        class Item:
            rank = 1
            ticker = "KO"
            rating = "B"
            total_score = 70.0
            rank_score = 68.5
            signal = "BUY"
            metrics = {"price": 55.0, "per": 18.0, "fcf_yield": 0.05, "ev_ebit": 20.0}

        row = daily_workflow._row_of(Item())
        assert row["price"] == 55.0
        assert row["rank_score"] == 68.5
        assert row["signal"] == "BUY"

    def test_row_of_graceful_without_metrics(self):
        from scripts import daily_workflow

        class Item:
            rank = 1
            ticker = "KO"
            rating = "B"
            total_score = 70.0
            rank_score = 68.5
            signal = "BUY"
            metrics = None

        row = daily_workflow._row_of(Item())
        assert row["price"] is None
        assert row["per"] is None

    def test_load_universe_csv(self, tmp_path):
        from scripts import daily_workflow

        f = tmp_path / "universe.csv"
        f.write_text(
            "ticker,cik,company_name,source_index\n"
            "AAPL,0000320193,Apple Inc.,SP500\n"
            "MSFT,0000789019,Microsoft Corp.,SP500\n",
            encoding="utf-8",
        )
        assert daily_workflow._load_universe(str(f)) == ["AAPL", "MSFT"]

    def test_parser_limit_flag(self):
        from scripts.daily_workflow import build_parser

        args = build_parser().parse_args(["--limit", "10"])
        assert args.limit == 10

    def test_parser_limit_default_none(self):
        from scripts.daily_workflow import build_parser

        args = build_parser().parse_args([])
        assert args.limit is None

    def test_parser_batch_flags(self):
        from scripts.daily_workflow import build_parser

        args = build_parser().parse_args(["--batch-size", "5", "--batch-delay", "0.1"])
        assert args.batch_size == 5
        assert args.batch_delay == 0.1