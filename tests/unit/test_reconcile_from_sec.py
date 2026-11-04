"""Regression tests for the SEC fiscal-year reconciliation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from scripts.reconcile_from_sec import (
    _iter_sec_facts,
    derive_fiscal_year,
    make_source_id,
    plan_changes,
    read_tickers_file,
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
    accn: str = BJRI_ACCN,
    sec_fy: int = 2025,
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
        "accn": accn,
        "sec_fy": sec_fy,
        "source_id": make_source_id(accn, namespace, concept, start, end),
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


@pytest.mark.parametrize(
    ("ticker", "sec_fy", "end", "fye_month", "expected"),
    [
        ("BJRI", 2023, "2025-12-30", 12, 2025),  # diff 2 -> override
        ("CNM", 2024, "2025-12-31", 12, 2024),  # diff 1 -> respect (start-year)
        ("KT", 2024, "2025-12-31", 12, 2024),  # diff 1 -> respect (20-F)
        ("IMOS", 2024, "2025-12-31", 12, 2024),  # diff 1 -> respect (20-F)
        ("WMT", 2025, "2026-01-31", 1, 2025),  # diff 1 -> respect (Jan FYE)
        ("AAPL", 2024, "2024-09-28", 9, 2024),  # diff 0 -> respect
        ("HD", 2025, "2026-02-01", 2, 2025),
        ("LOW", 2025, "2026-01-30", 1, 2025),
        ("TGT", 2025, "2026-01-31", 1, 2025),
        ("COST", 2025, "2025-08-31", 8, 2025),
    ],
)
def test_derive_fiscal_year(ticker, sec_fy, end, fye_month, expected):
    fact = {"fy": sec_fy, "end": end}
    assert derive_fiscal_year(fact, fye_month) == expected, ticker


def test_bucketing_overrides_an_absurd_sec_fy_for_bjri():
    fact = _sec_fact(sec_fy=2023)
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
    assert parsed[0]["sec_fy"] == 2023


def test_tickers_file_reads_lines_and_ignores_comments(tmp_path):
    path = tmp_path / "tickers.txt"
    path.write_text("AAPL\n\nMSFT  # second\n", encoding="utf-8")
    assert read_tickers_file(path) == ["AAPL", "MSFT"]
