"""Read-view derivation of total liabilities (assets - equity)."""

from __future__ import annotations

from datetime import date

from backend.services.financials_view_service import derive_liabilities


def _fact(concept: str, value: float, year: int = 2024) -> dict:
    return {
        "concept": concept,
        "value": value,
        "unit": "USD",
        "fiscal_year": year,
        "fiscal_period": "FY",
        "period_end": date(year, 12, 31),
    }


def test_derive_liabilities_when_the_tag_is_missing():
    facts, years = derive_liabilities(
        [
            _fact("Assets", 100_000_000),
            _fact("StockholdersEquity", 40_000_000),
        ],
        {2024},
    )

    derived = [fact for fact in facts if fact.get("derived")]
    assert years == [2024]
    assert len(derived) == 1
    assert derived[0]["concept"] == "Liabilities"
    assert derived[0]["value"] == 60_000_000


def test_derive_liabilities_does_not_override_a_reported_total():
    facts, years = derive_liabilities(
        [
            _fact("Assets", 100_000_000),
            _fact("Liabilities", 55_000_000),
            _fact("StockholdersEquity", 45_000_000),
        ],
        {2024},
    )

    assert years == []
    assert not any(fact.get("derived") for fact in facts)


def test_derive_liabilities_needs_both_assets_and_equity():
    facts, years = derive_liabilities([_fact("Assets", 100_000_000)], {2024})

    assert years == []
    assert not any(fact.get("derived") for fact in facts)


def test_derive_liabilities_ignores_years_outside_the_window():
    facts, years = derive_liabilities(
        [
            _fact("Assets", 100_000_000, year=2020),
            _fact("StockholdersEquity", 40_000_000, year=2020),
        ],
        {2024},
    )

    assert years == []
    assert not any(fact.get("derived") for fact in facts)
