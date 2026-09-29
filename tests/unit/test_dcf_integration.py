"""Tests for the supplementary ``not-from-canon`` DCF integration.

Covers the analyze-full section (present by default, optional via ``--no-dcf``,
never breaks on INSUFFICIENT_DATA), the daily report section (rendered after
``## Alerts``, before ``## Missing data``, never touching the ranking), the
``dcf:*`` toggles in config/refresh.yaml, the ``--no-dcf`` flag of
daily_workflow, and the regression guarantee that the DCF stays outside the
five book methodologies (no compare-methodologies / methodologies list entry).

The DCF module (``backend/valuation/``) is itself untouched here; it is only
consumed as a provider of supplementary output.
"""

from __future__ import annotations

import json
import pkgutil
from argparse import Namespace
from datetime import date
from pathlib import Path

import backend.methodologies
from backend.methodologies import discover, registry
from backend.services import refresh_service
from backend.services.daily_report_service import DailyReport, build_markdown
from backend.services.refresh_service import DCFConfig, load_dcf_config
from backend.valuation.base import DCFResult
from backend.valuation.dcf import INSUFFICIENT_DATA
from cli.commands import analyze_full
from scripts import daily_workflow

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ----------------------------------------------------------------------
# shared fakes
# ----------------------------------------------------------------------


class _Prices:
    """Minimal PriceService stub: three deterministic methods."""

    def __init__(self, price=338.4):
        self._price = price

    def get_current_price(self, ticker):
        return self._price

    def get_market_cap(self, ticker):
        return 5_000_000_000_000.0

    def get_beta(self, ticker):
        return 1.2


class _Repo:
    """Repository stub returning the rows of one fixture file."""

    def __init__(self, fixture="dcf_aapl_like.json"):
        self._fixture = fixture

    def get_best_available(self, ticker):
        return _rows(self._fixture)


def _rows(name: str):
    from backend.domain.value_objects.financials_normalized import NormalizedFinancials

    rows = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [NormalizedFinancials.from_dict(item) for item in rows]


def _success_result(ticker="AAPL") -> DCFResult:
    return DCFResult(
        ticker=ticker,
        intrinsic_value_per_share=140.35,
        current_price=338.40,
        margin_of_safety=-1.411,
        verdict="OVERVALUED",
        wacc=0.0937,
        fcf_base=100_000_000_000.0,
        fcf_years=3,
        growth_1_5=0.086,
        growth_6_10=0.043,
        terminal_growth=0.025,
        shares_outstanding=15_000_000_000.0,
    )


def _insufficient_result(ticker="F") -> DCFResult:
    return DCFResult(
        ticker=ticker,
        intrinsic_value_per_share=None,
        current_price=None,
        margin_of_safety=None,
        verdict=INSUFFICIENT_DATA,
        wacc=None,
        fcf_base=None,
        fcf_years=None,
        growth_1_5=None,
        growth_6_10=None,
        terminal_growth=0.025,
        shares_outstanding=None,
        reasons=["Negative FCF; DCF not applicable to cash-burning companies."],
        missing_inputs=["positive free cash flow"],
    )


def _analysis_dict():
    return {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "roe": 0.25,
        "roic": 0.2,
        "operating_margin": 0.31,
        "net_margin": 0.24,
        "revenue_growth": 0.06,
        "debt_to_equity": 0.5,
        "fcf": 90_000_000_000,
        "buffett_score": 82.0,
        "moat_analysis": {"moat_type": "MODERATE", "moat_score": 0.7},
        "composite_score": {
            "total_score": 78.0,
            "rating": "B",
            "confidence": "MEDIUM",
        },
        "dcf_value": 250.0,
        "dcf_margin_of_safety": 0.1,
        "anomalies": ["Margen bruto cayo en 2025"],
        "score": 0.82,
        "data_source_used": "MIXED",
        "data_quality_score": 0.9,
    }


def _screener_row():
    from backend.domain.value_objects.screener_result import ScreenerRow

    return ScreenerRow(
        ticker="AAPL",
        name="Apple Inc.",
        price=200.0,
        market_cap=1_000_000_000_000,
        per=10.0,
        pb=6.0,
        roe=0.25,
        roic=0.2,
        operating_margin=0.31,
        net_margin=0.24,
        fcf_yield=0.09,
        ev_ebit=12.0,
        debt_to_equity=0.4,
        revenue_growth=0.06,
        fcf=90_000_000_000,
        score=0.82,
        extra=_analysis_dict(),
    )


def _patch_analyze_full_deps(monkeypatch, row):
    """Hermetic substitutes for every dependency the analyzed report touches."""

    class _FakeService:
        def _analyze_ticker(self, ticker, no_prices=False):
            return row

    class _FakeHist:
        def format_valuation_table(self, ticker):
            return "     [tabla historica fake]"

    class _Company:
        sector = "Technology"
        industry = "Consumer Electronics"

    class _FakeCompanyRepo:
        def find_by_ticker(self, ticker):
            return _Company()

    monkeypatch.setattr(analyze_full, "build_screener_service", lambda: _FakeService())
    monkeypatch.setattr(
        analyze_full, "HistoricalValuationService", lambda: _FakeHist()
    )
    monkeypatch.setattr(analyze_full, "refresh_analysis_inputs", lambda *a, **k: None)
    monkeypatch.setattr(analyze_full, "CompanyRepository", lambda: _FakeCompanyRepo())


def _run_analyze_full(monkeypatch, repo_fixture, **extra_args):
    """Run analyze-full end-to-end with every data source stubbed."""
    monkeypatch.setattr(
        "backend.app.cli.build_financial_repository",
        lambda: _Repo(repo_fixture),
    )
    monkeypatch.setattr(
        "backend.services.price_service.get_price_service",
        lambda: _Prices(),
    )
    _patch_analyze_full_deps(monkeypatch, _screener_row())
    args = {"tickers": ["AAPL"], "no_prices": False}
    args.update(extra_args)
    analyze_full._run(Namespace(**args))


# ----------------------------------------------------------------------
# analyze-full section
# ----------------------------------------------------------------------


class TestAnalyzeFullDcf:
    def test_analyze_full_dcf_section_present(self, monkeypatch, capsys):
        """The DCF section appears by default, between quality and the
        historical valuation, labeled not-from-canon."""
        _run_analyze_full(monkeypatch, "dcf_aapl_like.json")
        out = capsys.readouterr().out
        assert "DCF Valuation (supplementary, not-from-canon)" in out
        assert "Intrinsic value/share" in out
        assert "NOT part of any book-derived methodology" in out
        assert out.index("DCF Valuation") < out.index("5) Valoracion historica")
        assert "6) Riesgos" in out

    def test_analyze_full_dcf_disabled(self, monkeypatch, capsys):
        """--no-dcf removes the section while the rest of the report stays."""
        _run_analyze_full(monkeypatch, "dcf_aapl_like.json", no_dcf=True)
        out = capsys.readouterr().out
        assert "DCF Valuation" not in out
        assert "not-from-canon" not in out
        assert "5) Valoracion historica" in out
        assert "6) Riesgos" in out

    def test_analyze_full_dcf_config_disables_section(self, monkeypatch, capsys):
        """config dcf.in_analyze_full=false hides it without --no-dcf."""
        monkeypatch.setattr(
            refresh_service, "load_dcf_config", lambda: DCFConfig(in_analyze_full=False)
        )
        _run_analyze_full(monkeypatch, "dcf_aapl_like.json")
        out = capsys.readouterr().out
        assert "DCF Valuation" not in out

    def test_analyze_full_dcf_insufficient(self, monkeypatch, capsys):
        """INSUFFICIENT_DATA shows the reason and the rest of the report is
        unchanged."""
        _run_analyze_full(monkeypatch, "dcf_negative_fcf.json")
        out = capsys.readouterr().out
        assert "DCF Valuation (supplementary, not-from-canon)" in out
        assert "INSUFFICIENT_DATA" in out
        assert "Negative FCF" in out
        assert "cash-burning companies" in out
        assert "Intrinsic value/share" not in out
        assert "5) Valoracion historica" in out
        assert "6) Riesgos" in out

    def test_analyze_full_dcf_unavailable_degrades(self, monkeypatch, capsys):
        """A raising DCF path prints 'DCF unavailable' and never stops the
        report."""
        monkeypatch.setattr(
            "backend.app.cli.build_financial_repository",
            lambda: _Repo("dcf_aapl_like.json"),
        )
        monkeypatch.setattr(
            "backend.services.price_service.get_price_service",
            lambda: _Prices(),
        )
        _patch_analyze_full_deps(monkeypatch, _screener_row())

        class Broken:
            def get_best_available(self, ticker):
                raise RuntimeError("db down")

        monkeypatch.setattr(
            "backend.app.cli.build_financial_repository", lambda: Broken()
        )
        analyze_full._run(Namespace(tickers=["AAPL"], no_prices=False))
        out = capsys.readouterr().out
        assert "DCF unavailable" in out
        assert "5) Valoracion historica" in out
        assert "6) Riesgos" in out

    def test_render_dcf_section_shows_values_and_assumptions(self, capsys):
        analyze_full.render_dcf_section(_success_result())
        out = capsys.readouterr().out
        assert "Intrinsic value/share" in out and "$140.35" in out
        assert "Margin of safety" in out
        assert "OVERVALUED" in out
        assert "WACC" in out and "Assumptions" in out
        assert "FCF base (3y avg)" in out
        assert "not-from-canon" in out

    def test_render_dcf_section_insufficient_shows_reason(self, capsys):
        analyze_full.render_dcf_section(_insufficient_result())
        out = capsys.readouterr().out
        assert "INSUFFICIENT_DATA" in out
        assert "Negative FCF" in out
        assert "Faltan" in out
        assert "NOT part of any book-derived methodology" in out


# ----------------------------------------------------------------------
# config toggles
# ----------------------------------------------------------------------


class TestDcfConfig:
    def test_load_dcf_config_defaults_when_file_missing(self, tmp_path, monkeypatch):
        for var in ("DCF_IN_ANALYZE_FULL", "DCF_IN_DAILY_REPORT", "DCF_DAILY_REPORT_TOP_N"):
            monkeypatch.delenv(var, raising=False)
        cfg = load_dcf_config(str(tmp_path / "no_such.yaml"))
        assert cfg.in_analyze_full is True
        assert cfg.in_daily_report is True
        assert cfg.daily_report_top_n == 10

    def test_load_dcf_config_reads_file_block(self, tmp_path, monkeypatch):
        for var in ("DCF_IN_ANALYZE_FULL", "DCF_IN_DAILY_REPORT", "DCF_DAILY_REPORT_TOP_N"):
            monkeypatch.delenv(var, raising=False)
        path = tmp_path / "refresh.yaml"
        path.write_text(
            "auto_refresh: false\n"
            "dcf:\n"
            "  in_analyze_full: false\n"
            "  in_daily_report: true\n"
            "  daily_report_top_n: 7\n",
            encoding="utf-8",
        )
        cfg = load_dcf_config(str(path))
        assert cfg.in_analyze_full is False
        assert cfg.in_daily_report is True
        assert cfg.daily_report_top_n == 7

    def test_load_dcf_config_block_ends_at_sibling_key(self, tmp_path, monkeypatch):
        for var in ("DCF_IN_ANALYZE_FULL", "DCF_IN_DAILY_REPORT", "DCF_DAILY_REPORT_TOP_N"):
            monkeypatch.delenv(var, raising=False)
        path = tmp_path / "refresh.yaml"
        path.write_text(
            "dcf:\n"
            "  daily_report_top_n: 5\n"
            "freshness_max_age_hours: 1\n",
            encoding="utf-8",
        )
        cfg = load_dcf_config(str(path))
        assert cfg.daily_report_top_n == 5

    def test_load_dcf_config_env_overrides(self, tmp_path, monkeypatch):
        path = tmp_path / "refresh.yaml"
        path.write_text("dcf:\n  in_daily_report: true\n  daily_report_top_n: 3\n", encoding="utf-8")
        monkeypatch.setenv("DCF_IN_DAILY_REPORT", "false")
        monkeypatch.setenv("DCF_DAILY_REPORT_TOP_N", "25")
        cfg = load_dcf_config(str(path))
        assert cfg.in_daily_report is False
        assert cfg.daily_report_top_n == 25


# ----------------------------------------------------------------------
# daily report section
# ----------------------------------------------------------------------


def _screened_row_row(rank=1, ticker="AAPL"):
    return {
        "rank": rank,
        "ticker": ticker,
        "name": f"Company {ticker}",
        "rating": "B",
        "total_score": 78.0 - rank,
        "rank_score": 62.0 - rank,
        "price": 200.0,
        "per": 18.0,
        "fcf_yield": 0.05,
        "ev_ebit": 14.0,
        "signal": "HOLD",
    }


def _daily_report(dcf_rows, rows=None, alerts=None):
    return DailyReport(
        report_date=date(2026, 9, 29),
        universe_size=10,
        screened_count=len(rows or []),
        sec_update="refresh: skipped (dry run)",
        prices_mode="real-time",
        rows=rows if rows is not None else [_screened_row_row(), _screened_row_row(2, "MSFT")],
        alerts=alerts
        if alerts is not None
        else [
            {
                "ticker": "AAPL",
                "alert_type": "BUY_SIGNAL",
                "confidence": "MEDIUM",
                "reason": ["criteria met"],
            }
        ],
        missing=["SKIPME"],
        dcf_rows=dcf_rows,
    )


class TestDailyReportDcf:
    def test_daily_report_dcf_section(self):
        dcf_rows = [
            {
                "ticker": "AAPL",
                "intrinsic": 140.35,
                "price": 338.40,
                "mos": -1.411,
                "verdict": "OVERVALUED",
                "reason": "",
            },
            {
                "ticker": "MSFT",
                "intrinsic": None,
                "price": None,
                "mos": None,
                "verdict": "INSUFFICIENT_DATA",
                "reason": "Negative FCF; DCF not applicable to cash-burning companies.",
            },
        ]
        body = build_markdown(_daily_report(dcf_rows))

        assert "## DCF Valuation (supplementary, not-from-canon)" in body
        assert "| AAPL | $140 | $338 | -141.1% | OVERVALUED |" in body
        assert "not-from-canon" in body
        # The insufficient reason surfaces under the table, not in a cell.
        assert "Negative FCF" in body
        # Placement: after `## Alerts`, before `## Missing data`.
        alerts_idx = body.index("## Alerts")
        dcf_idx = body.index("## DCF Valuation")
        missing_idx = body.index("## Missing data")
        assert alerts_idx < dcf_idx < missing_idx

    def test_daily_report_dcf_disabled(self):
        body = build_markdown(_daily_report(dcf_rows=[]))
        assert "## DCF Valuation" not in body
        assert "## Alerts" in body
        assert "## Missing data" in body

    def test_dcf_does_not_contaminate_ranking(self):
        """The top-opportunities (## Screened) block is byte-identical whether
        or not the supplementary DCF section is present."""
        rows = [_screened_row_row(1, "AAPL"), _screened_row_row(2, "MSFT")]
        dcf_rows = [
            {"ticker": "AAPL", "intrinsic": 140.35, "price": 338.40, "mos": -1.411, "verdict": "OVERVALUED", "reason": ""}
        ]
        with_dcf = build_markdown(_daily_report(dcf_rows=dcf_rows, rows=rows))
        without_dcf = build_markdown(_daily_report(dcf_rows=[], rows=rows))

        def screened_block(body: str) -> str:
            start = body.index("## Screened")
            end = body.index("## Alerts", start)
            return body[start:end]

        assert screened_block(with_dcf) == screened_block(without_dcf)
        assert "AAPL" in screened_block(with_dcf)
        assert "MSFT" in screened_block(with_dcf)


# ----------------------------------------------------------------------
# daily workflow --no-dcf and top-N
# ----------------------------------------------------------------------


class TestDailyWorkflowDcfRows:
    def test_daily_dcf_rows_respects_no_dcf_flag(self):
        rows = [_screened_row_row(), _screened_row_row(2, "MSFT")]
        assert daily_workflow._dcf_rows_for_report(rows, Namespace(no_dcf=True), None, object()) == []

    def test_daily_dcf_rows_disabled_by_config(self, monkeypatch):
        monkeypatch.setattr(
            refresh_service, "load_dcf_config", lambda: DCFConfig(in_daily_report=False)
        )
        rows = [_screened_row_row()]
        assert daily_workflow._dcf_rows_for_report(rows, Namespace(no_dcf=False), None, object()) == []

    def test_daily_dcf_rows_top_n(self, monkeypatch):
        monkeypatch.setattr(
            refresh_service, "load_dcf_config", lambda: DCFConfig(daily_report_top_n=2)
        )
        rows = [_screened_row_row(1, "AAPL"), _screened_row_row(2, "MSFT"), _screened_row_row(3, "KO")]
        dcf_rows = daily_workflow._dcf_rows_for_report(
            rows, Namespace(no_dcf=False), _Repo("dcf_aapl_like.json"), _Prices()
        )
        assert [r["ticker"] for r in dcf_rows] == ["AAPL", "MSFT"]
        assert all(r["verdict"] != "ERROR" for r in dcf_rows)

    def test_daily_dcf_rows_error_isolated(self, monkeypatch):
        monkeypatch.setattr(
            refresh_service, "load_dcf_config", lambda: DCFConfig()
        )

        class _Broken:
            def get_best_available(self, ticker):
                raise RuntimeError("db down")

        dcf_rows = daily_workflow._dcf_rows_for_report(
            [{"ticker": "AAPL"}], Namespace(no_dcf=False), _Broken(), _Prices()
        )
        assert dcf_rows == [
            {"ticker": "AAPL", "verdict": "ERROR", "reason": "DCF failed: db down"}
        ]


# ----------------------------------------------------------------------
# regression: the DCF is NOT a methodology
# ----------------------------------------------------------------------


class TestDcfStaysOutsideMethodologies:
    def test_compare_methodologies_still_excludes_dcf(self):
        discover()
        names = registry.list()
        assert set(names) == {
            "buffett_clark",
            "buffett_classic",
            "fisher_quantitative_subset",
            "graham",
            "graham_dodd",
            "lynch_garp",
        }
        assert not any("dcf" in name.lower() for name in names)

    def test_dcf_module_never_discovered(self):
        """backend/valuation is not a subpackage of backend/methodologies, so
        auto-discovery can never register it."""
        mods = {
            info.name
            for info in pkgutil.iter_modules(backend.methodologies.__path__)
        }
        assert "valuation" not in mods