"""Unit tests for the analyze-full consolidated report command."""

from argparse import Namespace
from unittest.mock import Mock

import pytest

from backend.domain.value_objects.screener_result import ScreenerRow
from backend.services.screener_service import StockScreenerService
from cli.commands import analyze_full


def _analysis_dict(**overrides):
    base = {
        "ticker": "AAPL",
        "roe": 0.25,
        "roic": 0.2,
        "operating_margin": 0.31,
        "net_margin": 0.24,
        "revenue_growth": 0.06,
        "debt_to_equity": 0.5,
        "fcf": 90_000_000_000,
        "owner_earnings": 85_000_000_000,
        "croic": 0.15,
        "buffett_score": 82.0,
        "moat_analysis": {"moat_type": "MODERATE", "moat_score": 0.7},
        "composite_score": {
            "total_score": 78.0,
            "rating": "B",
            "confidence": "MEDIUM",
        },
        "dcf_value": 250.0,
        "dcf_margin_of_safety": 0.1,
        "quality_metrics": {"roic_mean": 0.19, "revenue_cagr": 0.07},
        "insight": "Rentabilidad sostenida por encima del objetivo.",
        "anomalies": ["Margen bruto cayo en 2025"],
        "piotroski_fscore": 7,
        "altman_zscore": 4.2,
        "score": 0.82,
        "data_source_used": "MIXED",
        "data_quality_score": 0.9,
        "ebit": 120_000_000_000,
        "total_debt": 100_000_000_000,
        "cash_and_equivalents": 30_000_000_000,
        "net_income": 100_000_000_000,
    }
    base.update(overrides)
    return base


class TestAnalyzeFullSections:
    def test_section_overview(self, capsys):
        analyze_full._section_overview(
            {"ticker": "AAPL", "name": "Apple Inc."},
            "Technology",
            "Consumer Electronics",
        )
        out = capsys.readouterr().out
        assert "Apple Inc." in out
        assert "Technology" in out
        assert "Consumer Electronics" in out

    def test_section_price_renders_n_a_when_missing(self, capsys):
        analyze_full._section_price(None, None, None, None, None, None, None, False)
        out = capsys.readouterr().out
        assert "Price" in out
        assert "N/A" in out

    def test_section_price_marks_no_prices_mode(self, capsys):
        analyze_full._section_price(None, None, None, None, None, None, None, True)
        out = capsys.readouterr().out
        assert "--no-prices" in out

    def test_section_quality_uses_composite(self, capsys):
        analyze_full._section_quality(_analysis_dict(), {})
        out = capsys.readouterr().out
        assert "Buffett score" in out
        assert "MODERATE" in out
        assert "Rentabilidad sostenida" in out

    def test_section_risks_lists_anomalies_and_sources(self, capsys):
        analyze_full._section_risks(_analysis_dict())
        out = capsys.readouterr().out
        assert "Anomaly:" in out
        assert "Margen bruto cayo" in out
        assert "Source: MIXED" in out

    def test_section_risks_no_anomalies_when_empty(self, capsys):
        analyze_full._section_risks(_analysis_dict(anomalies=[]))
        out = capsys.readouterr().out
        assert "No anomalies detected." in out


class TestAnalyzeFullRunner:
    def _fake_service(self, row, side_effect=None):
        class Fake:
            def _analyze_ticker(self, ticker, no_prices=False):
                if side_effect:
                    raise side_effect
                return row

        return Fake()

    def _args(self, tickers=("AAPL", "MSFT")):
        return Namespace(tickers=list(tickers), no_prices=False)

    def test_runner_prints_error_then_continues(self, monkeypatch, capsys):
        class Broken:
            def _analyze_ticker(self, ticker, no_prices=False):
                raise ValueError("boom")

        monkeypatch.setattr(analyze_full, "build_screener_service", lambda: Broken())
        analyze_full._run(self._args())
        out = capsys.readouterr().out
        assert "ERROR" in out
        assert out.count("boom") == 2  # both tickers attempted, none stops

    def test_runner_reports_missing_data(self, monkeypatch, capsys):
        class Empty:
            def _analyze_ticker(self, ticker, no_prices=False):
                return None

        monkeypatch.setattr(analyze_full, "build_screener_service", lambda: Empty())
        analyze_full._run(self._args())
        out = capsys.readouterr().out
        assert "Not enough data for" in out

    def test_runner_renders_all_sections(self, monkeypatch, capsys):
        row = ScreenerRow(
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
        service = self._fake_service(row)
        monkeypatch.setattr(analyze_full, "build_screener_service", lambda: service)

        class _FakeHist:
            def format_valuation_table(self, ticker):
                return "     [tabla historica fake]"

        monkeypatch.setattr(
            analyze_full, "HistoricalValuationService", lambda: _FakeHist()
        )

        analyze_full._run(self._args(tickers=("AAPL",)))

        out = capsys.readouterr().out
        assert "1) Company overview" in out
        assert "Apple Inc." in out
        assert "2) Real-time price and valuation" in out
        assert "$1,000" in out or "$1" in out
        assert "3) Fundamental metrics" in out
        assert "4) Company quality" in out
        assert "5) Historical valuation" in out
        assert "tabla historica fake" in out
        assert "6) Risks / anomalies / triggers" in out


class TestAnalyzeFullMockedPrice:
    """The real-time price reaches the report through the real
    `_analyze_ticker` wiring with a mocked PriceService (deterministic);
    the analytics layer is stubbed so the flow stays DB-free."""

    def _build_service(self, price=200.0, shares=5_000_000_000):
        analysis = _analysis_dict()
        analysis.update(
            {
                "shares_outstanding": None,
                "market_cap": None,
                "per": None,
                "pb": None,
                "fcf_yield": None,
                "ev_ebit": None,
                "net_income": 100_000_000_000,
                "ebit": 120_000_000_000,
                "total_debt": 100_000_000_000,
                "cash_and_equivalents": 30_000_000_000,
                "fcf": 90_000_000_000,
            }
        )
        repo = Mock()
        market = Mock()
        market.get_company_name.return_value = "Apple Inc."
        prices = Mock()
        prices.get_current_price.return_value = price
        prices.get_shares_outstanding.return_value = shares
        service = StockScreenerService(
            repository=repo, market_provider=market, price_service=prices
        )
        service._analysis.analyze = Mock(return_value=analysis)
        return service, prices

    def _patch_deps(self, monkeypatch, service):
        monkeypatch.setattr(analyze_full, "build_screener_service", lambda: service)
        monkeypatch.setattr(
            analyze_full, "refresh_analysis_inputs", lambda *a, **k: None
        )

        class _FakeHist:
            def format_valuation_table(self, ticker):
                return "     [tabla historica fake]"

        monkeypatch.setattr(
            analyze_full, "HistoricalValuationService", lambda: _FakeHist()
        )

    def test_runner_renders_realtime_price_from_price_service(
        self, monkeypatch, capsys
    ):
        """Section 2 shows the mocked price and the valuation metrics derived
        from it (P/E, FCF yield, EV/EBIT) — i.e. the row price is not
        hard-coded or dropped, it flows through the PriceService."""
        service, prices = self._build_service()
        self._patch_deps(monkeypatch, service)

        analyze_full._run(
            Namespace(
                tickers=["AAPL"],
                no_prices=False,
                refresh=False,
                no_refresh=False,
                freshness_hours=None,
            )
        )

        out = capsys.readouterr().out
        prices.get_current_price.assert_called_once_with("AAPL")
        assert "2) Real-time price and valuation" in out
        # 200.0 * 5e9 = 1e12 market cap -> P/E 10.0, FCF yield 9.0%, EV/EBIT 8.9
        assert "$200.00" in out
        assert "PER" in out and "10.0" in out
        assert "9.0%" in out
        assert "EV/EBIT" in out and "8.9" in out
        assert "6) Risks / anomalies / triggers" in out

    def test_runner_no_prices_never_calls_price_service(self, monkeypatch, capsys):
        """With --no-prices the PriceService is never consulted and section 2
        says so — real-time prices stay optional for the report."""
        service, prices = self._build_service()
        self._patch_deps(monkeypatch, service)

        analyze_full._run(
            Namespace(
                tickers=["AAPL"],
                no_prices=True,
                refresh=False,
                no_refresh=False,
                freshness_hours=None,
            )
        )

        out = capsys.readouterr().out
        prices.get_current_price.assert_not_called()
        prices.get_shares_outstanding.assert_not_called()
        assert "--no-prices" in out


if __name__ == "__main__":
    pytest.main([__file__])
