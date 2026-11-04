"""Regression tests for the SEC fiscal-year reconciliation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from scripts.reconcile_from_sec import (
    _iter_sec_facts,
    derive_fiscal_year,
    infer_offset_from_history,
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
    ("ticker", "offset", "end", "sec_fy", "expected", "source"),
    [
        ("BJRI", 0, "2025-12-30", 2023, 2025, "mode_history"),
        ("CNM", -1, "2025-02-02", 2023, 2024, "mode_history"),
        ("IMOS", 0, "2023-12-31", 2024, 2023, "mode_history"),
        ("KT", 0, "2023-12-31", 2023, 2023, "mode_history"),
        ("WMT", 0, "2026-01-31", 2025, 2026, "mode_history"),
        ("TGT", -1, "2026-01-31", 2025, 2025, "mode_history"),
        ("HD", -1, "2026-02-01", 2025, 2025, "mode_history"),
        ("LOW", -1, "2026-01-30", 2025, 2025, "mode_history"),
        ("COST", 0, "2025-08-31", 2025, 2025, "mode_history"),
        ("AAPL", 0, "2024-09-28", 2024, 2024, "mode_history"),
        ("NO_HISTORY", None, "2025-12-30", 2024, 2024, "fallback_fy"),
        ("SANITY", 0, "2025-12-30", 2018, 2018, "fallback_sanity"),
    ],
)
def test_derive_fiscal_year(ticker, offset, end, sec_fy, expected, source):
    assert derive_fiscal_year({"end": end}, offset, sec_fy) == (
        expected,
        source,
    ), ticker


def test_infer_offset_uses_the_dominant_convention():
    pairs = [(2024, 2024), (2023, 2023), (2022, 2022), (2021, 2022)]
    assert infer_offset_from_history(pairs, current_year=2026) == 0


def test_infer_offset_breaks_a_tie_towards_zero():
    pairs = [(2024, 2025), (2023, 2024), (2022, 2022), (2021, 2021)]
    assert infer_offset_from_history(pairs, current_year=2026) == 0


def test_infer_offset_returns_none_without_enough_years():
    assert infer_offset_from_history([(2024, 2024)], current_year=2026) is None


def test_infer_offset_ignores_years_outside_the_window():
    pairs = [
        (2015, 2016),
        (2016, 2017),
        (2021, 2021),
        (2022, 2022),
        (2023, 2023),
    ]
    assert infer_offset_from_history(pairs, lookback_years=5, current_year=2026) == 0


def test_bucketing_overrides_an_absurd_sec_fy_for_bjri():
    fact = _sec_fact(sec_fy=2023)
    plan = plan_changes(
        "BJRI", "company", "1013488", 12, 0, [fact], _existing(fact["source_id"], 2023)
    )

    assert plan.updates[0].new_fiscal_year == 2025
    assert plan.updates[0].old_fiscal_year == 2023
    assert plan.updates[0].offset_applied == 0
    assert plan.updates[0].offset_source == "mode_history"


def test_plan_respects_the_company_offset_for_cnm():
    fact = _sec_fact(
        start=date(2025, 2, 3),
        end=date(2025, 2, 2),
        sec_fy=2023,
    )
    plan = plan_changes(
        "CNM",
        "company",
        "1856525",
        1,
        -1,
        [fact],
        _existing(fact["source_id"], 2023),
    )

    assert plan.updates[0].new_fiscal_year == 2024
    assert plan.updates[0].offset_source == "mode_history"


def test_plan_inserts_a_missing_annual_fact():
    fact = _sec_fact()
    plan = plan_changes("BJRI", "company", "1013488", 12, 0, [fact], [])

    assert plan.inserts and not plan.updates
    assert plan.inserts[0].new_fiscal_year == 2025


def test_plan_is_idempotent_once_the_year_is_correct():
    fact = _sec_fact()
    plan = plan_changes(
        "BJRI", "company", "1013488", 12, 0, [fact], _existing(fact["source_id"], 2025)
    )

    assert not plan.updates and not plan.inserts
    assert plan.skipped == 1


def test_plan_matches_by_period_when_the_source_id_differs():
    fact = _sec_fact()
    plan = plan_changes(
        "BJRI", "company", "1013488", 12, 0, [fact], _existing("legacy-source", 2023)
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


# ---------------------------------------------------------------------------
# Atomic balance groups (company_id, period_end)
# ---------------------------------------------------------------------------
from scripts.reconcile_from_sec import plan_group, plan_ticker

GROUP_END = date(2025, 2, 2)
GROUP_START = date(2024, 2, 3)


def _group_fact(concept, value, *, end=GROUP_END, start=GROUP_START, fy=2023):
    return {
        "id": f"{concept}-{end}",
        "concept": concept,
        "value": value,
        "fiscal_year": fy,
        "period_start": start,
        "period_end": end,
    }


def _sec_index(facts, sec_fy):
    return {
        (fact["concept"], fact["period_start"], fact["period_end"]): {
            "concept": fact["concept"],
            "period_start": fact["period_start"],
            "period_end": fact["period_end"],
            "sec_fy": sec_fy,
        }
        for fact in facts
    }


def _balance_group(*, assets=100.0, liab=40.0, equity=60.0, end=GROUP_END, fy=2023):
    return [
        _group_fact("Assets", assets, end=end, fy=fy),
        _group_fact("Liabilities", liab, end=end, fy=fy),
        _group_fact("StockholdersEquity", equity, end=end, fy=fy),
    ]


def test_group_with_unanimous_year_moves():
    facts = _balance_group()
    result = plan_group(GROUP_END, facts, _sec_index(facts, 2023), -1)

    assert result.moved is True
    assert result.fiscal_year == 2024
    assert result.reason == "ok"


def test_group_with_discrepancy_skips():
    facts = _balance_group()
    index = _sec_index(facts, 2023)
    index[("Liabilities", GROUP_START, GROUP_END)]["sec_fy"] = 2018
    result = plan_group(GROUP_END, facts, index, -1)

    assert result.moved is False
    assert result.reason == "intra_group_discrepancy"


def test_group_with_balance_break_skips():
    facts = _balance_group(assets=100.0, liab=90.0, equity=60.0)
    result = plan_group(GROUP_END, facts, _sec_index(facts, 2023), -1)

    assert result.moved is False
    assert result.reason == "balance_would_break"


def test_group_with_missing_components_skips():
    facts = [
        _group_fact("Assets", 100.0),
        _group_fact("Liabilities", 40.0),
    ]
    result = plan_group(GROUP_END, facts, _sec_index(facts, 2023), -1)

    assert result.moved is False
    assert result.reason == "missing_components"


def test_ticker_with_mixed_groups_partial_success():
    good_end = GROUP_END
    bad_end = date(2024, 2, 1)
    good = _balance_group(end=good_end)
    bad = [
        _group_fact("Assets", 50.0, end=bad_end),
        _group_fact("StockholdersEquity", 20.0, end=bad_end),
    ]
    facts = good + bad
    index = _sec_index(good, 2023) | _sec_index(bad, 2023)

    report, moves = plan_ticker("TEST", "company", facts, list(index.values()), -1)

    assert report.reason == "ok"
    assert len(report.moved_groups) == 1
    assert len(report.skipped_groups) == 1
    assert moves == {good_end: 2024}


def test_reconcile_idempotent_after_the_move():
    facts = _balance_group(fy=2024)
    index = _sec_index(facts, 2024)

    report, moves = plan_ticker("TEST", "company", facts, list(index.values()), -1)

    assert moves == {}
    assert any(result.reason == "already_correct" for result in report.skipped_groups)
