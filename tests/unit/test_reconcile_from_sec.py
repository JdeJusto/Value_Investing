"""Regression tests for the SEC fiscal-year reconciliation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from scripts.reconcile_from_sec import (
    _iter_sec_facts,
    derive_fiscal_year,
    make_source_id,
    plan_changes,
)

BJRI_END = date(2025, 12, 30)
BJRI_START = date(2025, 1, 1)
BJRI_ACCN = "0001193125-26-083331"


def _sec_fact(
    *,
    concept: str = "Revenues",
    namespace: str = "us-gaap",
    start: date | None = BJRI_START,
    end: date = BJRI_END,
    value: str = "1200000000",
) -> dict:
    return {
        "concept": concept,
        "namespace": namespace,
        "value": Decimal(value),
        "unit": "USD",
        "period_start": start,
        "period_end": end,
        "form": "10-K",
        "filed": date(2026, 3, 2),
        "accn": BJRI_ACCN,
        "source_id": make_source_id(BJRI_ACCN, namespace, concept, start, end),
    }


def _existing(source_id: str, fiscal_year: int) -> list[dict]:
    return [
        {
            "id": "row-1",
            "concept": "Revenues",
            "period_start": BJRI_START,
            "period_end": BJRI_END,
            "source_id": source_id,
            "fiscal_year": fiscal_year,
        }
    ]


def test_bucketing_assigns_correct_fiscal_year_from_end_date():
    """BJRI's FY2025 10-K carries SEC fy=2023; the end date wins."""
    fact = _sec_fact()
    fact["fy"] = 2023  # presentation year, deliberately wrong for bucketing
    plan = plan_changes(
        "BJRI", "company", "1013488", 12, [fact], _existing(fact["source_id"], 2023)
    )

    assert plan.updates[0].new_fiscal_year == 2025
    assert plan.updates[0].old_fiscal_year == 2023


def test_plan_inserts_a_missing_annual_fact():
    fact = _sec_fact()
    plan = plan_changes("BJRI", "company", "1013488", 12, [fact], [])

    assert plan.inserts and not plan.updates
    assert plan.inserts[0].new_fiscal_year == 2025


def test_plan_is_idempotent_once_the_year_is_correct():
    fact = _sec_fact()
    plan = plan_changes(
        "BJRI", "company", "1013488", 12, [fact], _existing(fact["source_id"], 2025)
    )

    assert not plan.updates and not plan.inserts
    assert plan.skipped == 1


def test_plan_matches_by_period_when_the_source_id_differs():
    fact = _sec_fact()
    plan = plan_changes(
        "BJRI", "company", "1013488", 12, [fact], _existing("legacy-source", 2023)
    )

    assert plan.updates and plan.updates[0].row_id == "row-1"


def test_source_id_matches_the_fdb_audit_key():
    assert (
        make_source_id(BJRI_ACCN, "us-gaap", "Revenues", BJRI_START, BJRI_END)
        == f"{BJRI_ACCN}|us-gaap:Revenues|2025-01-01|2025-12-30"
    )
    assert (
        make_source_id(BJRI_ACCN, "us-gaap", "Assets", None, BJRI_END)
        == f"{BJRI_ACCN}|us-gaap:Assets|2025-12-30"
    )


def test_iter_sec_facts_keeps_only_annual_filings():
    facts = {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {
                            "end": "2025-12-30",
                            "start": "2025-01-01",
                            "val": 1_200_000_000,
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2026-03-02",
                            "accn": BJRI_ACCN,
                        },
                        {
                            "end": "2025-09-30",
                            "start": "2025-07-01",
                            "val": 300_000_000,
                            "fy": 2026,
                            "fp": "Q3",
                            "form": "10-Q",
                            "filed": "2025-11-01",
                            "accn": "q3-accn",
                        },
                    ]
                }
            }
        }
    }

    parsed = _iter_sec_facts(facts, date(2023, 1, 1))

    assert len(parsed) == 1
    assert parsed[0]["period_end"] == BJRI_END
    assert parsed[0]["source_id"].endswith("|2025-01-01|2025-12-30")


def test_derive_fiscal_year_uses_the_fiscal_year_end_month():
    assert derive_fiscal_year(date(2025, 12, 30), 12) == 2025
    assert derive_fiscal_year(date(2026, 1, 31), 12) == 2026
    # A period after the January year-end belongs to the next label.
    assert derive_fiscal_year(date(2026, 2, 1), 1) == 2027
