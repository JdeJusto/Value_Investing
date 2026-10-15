"""Phase B: the offline demo bundle feeds the scorecard.

The demo repository stores pinned *normalized* rows, while the insights,
alerts and scorecard read raw facts (``list_all_facts``). These tests pin the
re-emission bridge and the outcome users see: a demo scorecard with real
numbers instead of an all-``INSUFFICIENT`` card.
"""

from __future__ import annotations

from backend.repositories.fdb_concept_mapping import FIELD_CONCEPT
from backend.services.demo_mode import (
    DEMO_FUNDAMENTALS,
    DEMO_TICKERS,
    DemoFinancialRepository,
    DemoPriceService,
    is_demo,
    is_demo_ticker,
)
from backend.services.scorecard_service import ScorecardService


def _repository() -> DemoFinancialRepository:
    return DemoFinancialRepository(DEMO_FUNDAMENTALS)


def test_bundle_exposes_the_eight_tickers():
    assert len(DEMO_TICKERS) == 8
    assert all(is_demo_ticker(ticker) for ticker in DEMO_TICKERS)


def test_field_concept_covers_the_fundamental_fields():
    for field in ("revenue", "net_income", "operating_cash_flow", "dividends_paid"):
        assert FIELD_CONCEPT.get(field), field


def test_list_all_facts_re_emits_every_pinned_year():
    repository = _repository()
    facts = repository.list_all_facts("AAPL", "FY")
    years = {fact["fiscal_year"] for fact in facts}
    assert years == set(range(2016, 2026))
    assert {fact["fiscal_period"] for fact in facts} == {"FY"}
    revenue = {
        fact["fiscal_year"]: fact["value"]
        for fact in facts
        if fact["concept"] == "Revenues"
    }
    assert revenue[2025] == 416_000_000_000.0


def test_list_all_facts_is_stable_across_sources_and_calls():
    repository = _repository()
    first = repository.list_all_facts("AAPL", "FY")
    second = repository.list_all_facts("AAPL", "FY")
    assert first == second


def test_other_periods_are_empty():
    facts = _repository().list_all_facts("AAPL", "Q1")
    assert facts == []


def test_scorecard_computes_for_every_demo_ticker():
    """At least four of six dimensions are numeric (not ``None``/empty)."""
    repository = _repository()
    service = ScorecardService(repository=repository, price_service=DemoPriceService())
    for ticker in DEMO_TICKERS:
        card = service.build(ticker)
        assert card is not None, ticker
        numeric = [dim for dim in card.dimensions if dim.score is not None]
        assert len(numeric) >= 4, f"{ticker}: {len(numeric)}/6"
        assert any(dim.evaluable_rules for dim in card.dimensions)


def test_demo_scorecard_is_deterministic():
    service = ScorecardService(
        repository=_repository(), price_service=DemoPriceService()
    )
    assert service.build("AAPL").to_dict() == service.build("AAPL").to_dict()


def test_is_demo_reads_the_flag(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    assert is_demo()
    monkeypatch.delenv("VI_DEMO")
    assert not is_demo()
