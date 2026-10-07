"""NOT_APPLICABLE ("N/A") verdict for financial companies (v0.13.1).

A book screen written for product companies abstains on banks and insurers:
the verdict is ``N/A`` (excluded by design), NOT ``INSUFFICIENT_DATA`` (the
data to decide is missing). Every methodology must agree, the consensus must
count and exclude those rows, and the screener must show ``N/A``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import FINANCIAL_NA_REASON, Verdict
from backend.methodologies.buffett_clark.methodology import BuffettClarkMethodology
from backend.methodologies.buffett_classic.methodology import BuffettClassicMethodology
from backend.methodologies.fisher_quantitative_subset.methodology import (
    FisherQuantitativeSubsetMethodology,
)
from backend.methodologies.graham.methodology import GrahamMethodology
from backend.methodologies.graham_dodd.methodology import GrahamDoddMethodology
from backend.methodologies.greenblatt.methodology import GreenblattMethodology
from backend.methodologies.lynch_garp.methodology import LynchGARPMethodology
from backend.methodologies.marks.methodology import MarksMethodology
from backend.services.consensus_service import CompanyConsensus
from backend.services.ui_adapter import enrich_rows, run_methodologies
from scripts.compute_consensus_rankings import build_company_consensus


class _Prices:
    """Minimal price stub (the financial guard never reads it)."""

    def __init__(self, price: float | None = None) -> None:
        self._price = price

    def get_current_price(self, ticker: str) -> float | None:
        return self._price


ALL_METHODOLOGIES = [
    GrahamMethodology(),
    GrahamDoddMethodology(),
    BuffettClassicMethodology(),
    BuffettClarkMethodology(),
    FisherQuantitativeSubsetMethodology(),
    LynchGARPMethodology(),
    MarksMethodology(),
    GreenblattMethodology(),
]


def _financial_row(ticker: str) -> list[NormalizedFinancials]:
    return [
        NormalizedFinancials(
            ticker=ticker,
            fiscal_year=2024,
            period="FY",
            sector="Financial Services",
            net_income=10e9,
            total_assets=500e9,
            total_liabilities=470e9,
        )
    ]


@pytest.mark.parametrize("methodology", ALL_METHODOLOGIES, ids=lambda m: m.name)
@pytest.mark.parametrize("ticker", ["JPM", "BAC", "WFC"])
def test_every_methodology_returns_na_for_a_bank(methodology, ticker):
    result = methodology.evaluate(ticker, _financial_row(ticker), _Prices(100.0))
    assert result.verdict is Verdict.NOT_APPLICABLE
    assert result.score is None
    assert result.metrics["financial_company"] is True
    assert FINANCIAL_NA_REASON in result.reasons
    # Not a data gap: the canonical financial reason is present.
    assert not any("verdict: INSUFFICIENT_DATA" in reason for reason in result.reasons)


@pytest.mark.parametrize("methodology", ALL_METHODOLOGIES, ids=lambda m: m.name)
def test_non_financial_company_is_not_na(methodology):
    rows = [
        NormalizedFinancials(
            ticker="AAPL",
            fiscal_year=2024,
            period="FY",
            sector="Technology",
            revenue=100e9,
            net_income=20e9,
            operating_cash_flow=25e9,
            total_assets=200e9,
            total_liabilities=80e9,
        )
    ]
    result = methodology.evaluate("AAPL", rows, _Prices(100.0))
    assert result.verdict is not Verdict.NOT_APPLICABLE


def test_screener_row_shows_na_for_a_bank():
    def load_fundamentals(ticker):
        return _financial_row(ticker)

    rows = enrich_rows(
        [{"ticker": "JPM", "price": 200.0, "name": "JPMorgan Chase"}],
        "buffett_classic",
        {"JPM": "Financial Services"},
        load_fundamentals,
        run_methodologies,
        workers=1,
    )
    assert rows[0]["Verdict"] == "N/A"
    assert rows[0]["Category"] is None
    assert rows[0]["Sector"] == "Financial Services"


def test_consensus_counts_and_excludes_na_companies():
    view = SimpleNamespace(
        details=[
            {"methodology": key, "verdict": "N/A", "score": None}
            for key in (
                "graham",
                "graham_dodd",
                "buffett_classic",
                "buffett_clark",
                "fisher_quantitative_subset",
                "lynch_garp",
                "marks",
                "greenblatt",
            )
        ]
    )
    row = build_company_consensus("JPM", "JPMorgan Chase", view)
    assert row["na_count"] == 8
    assert row["insufficient_count"] == 0
    assert row["buy_count"] == 0

    company = CompanyConsensus(
        ticker="JPM",
        name="JPMorgan Chase",
        lynch_category="UNKNOWN",
        verdicts=row["verdicts"],
        buy_count=0,
        avoid_count=0,
        insufficient_count=0,
        consensus_score=0,
        na_count=8,
    )
    assert company.is_not_applicable is True
    assert company.is_excluded is True
    # An all-INSUFFICIENT data hole is still excluded (unchanged behaviour).
    hole = CompanyConsensus(
        ticker="XYZ",
        name="XYZ",
        lynch_category="UNKNOWN",
        verdicts={k: "INSUFFICIENT_DATA" for k in row["verdicts"]},
        buy_count=0,
        avoid_count=0,
        insufficient_count=8,
        consensus_score=0,
    )
    assert hole.is_data_hole is True
    assert hole.is_excluded is True


def test_na_count_is_derived_from_verdicts_when_absent(tmp_path):
    """Files written before v0.13.1 (no ``na_count``) still exclude all-N/A."""
    import json
    from datetime import UTC, datetime

    from backend.services.consensus_service import ConsensusService

    payload = {
        "date": datetime.now(UTC).date().isoformat(),
        "universe": "sp500",
        "version": 2,
        "companies": {
            "JPM": {
                "name": "JPMorgan Chase",
                "verdicts": {k: "N/A" for k in ("graham", "marks")},
                "buy_count": 0,
                "avoid_count": 0,
                "insufficient_count": 0,
                "consensus_score": 0,
                "lynch_category": "UNKNOWN",
                "price": None,
                "prices_available": False,
            }
        },
    }
    path = tmp_path / f"consensus_{payload['date']}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    service = ConsensusService(directory=tmp_path)
    report = service.load_latest()
    assert report is not None
    jpm = report.companies[0]
    assert jpm.na_count == 2
    assert jpm.is_not_applicable is True
    assert service.top_by_consensus(10) == []
