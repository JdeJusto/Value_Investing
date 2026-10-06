"""Pure helpers of the concept coverage audit (no database)."""

from __future__ import annotations

from scripts.audit_concept_coverage import (
    PROPOSED_FIELD,
    actionable_coverage,
    classify,
    mapped_concepts,
    render_markdown,
)

SAMPLE = [
    ("Revenues", 5_000, 10_000),
    ("SecuredDebt", 466, 900),
    ("WeightedAverageNumberOfDilutedSharesOutstanding", 5_489, 20_000),
    ("EntityPublicFloat", 5_138, 61_567),
    ("TinyConcept", 10, 12),
]


def test_mapped_concepts_include_core_and_recent_aliases():
    mapped = mapped_concepts()
    assert {"Revenues", "NetIncomeLoss", "SecuredDebt"} <= mapped
    assert "EntityPublicFloat" not in mapped


def test_classify_buckets_by_name():
    assert classify("NetIncomeLoss") == "income_profit"
    assert classify("EffectiveIncomeTaxRateContinuingOperations") == "tax"
    assert classify("OperatingLeaseLiability") == "industry"
    assert classify("LongTermDebtCurrent") == "balance_liabilities"
    assert classify("EntityPublicFloat") == "note_disclosure"


def test_actionable_coverage_is_the_mapped_share():
    assert actionable_coverage(42, 17) == 42 / 59 * 100
    assert actionable_coverage(0, 0) == 100.0


def test_render_markdown_reports_actionable_and_informational_counts():
    report = render_markdown(
        SAMPLE,
        top=300,
        min_companies=50,
        active_companies=6_736,
        missing_mapped=["StockholdersEquityNoteStockSplitConversionRatio"],
        generated="2026-10-06",
    )
    assert "Active listed companies with facts: **6,736**" in report
    assert "Mapped: **2**" in report
    assert "Unmapped with a proposed field (actionable): **1**" in report
    assert (
        "| `WeightedAverageNumberOfDilutedSharesOutstanding` | 5,489 | 20,000 | "
        "shares_outstanding |" in report
    )
    assert "EntityPublicFloat" in report
    assert "`StockholdersEquityNoteStockSplitConversionRatio`" in report


def test_render_markdown_marks_mapped_and_unmapped_rows():
    report = render_markdown(
        SAMPLE,
        top=10,
        min_companies=50,
        active_companies=1,
        missing_mapped=[],
        generated="2026-10-06",
    )
    assert "| `Revenues` | 5,000 | 10,000 | ✓ |" in report
    assert "| `EntityPublicFloat` | 5,138 | 61,567 | ✗ |" in report
    # The tiny concept is below the min-companies filter: not listed as high
    # coverage, but it still shapes the full sample table.
    assert "TinyConcept" in report


def test_proposed_field_covers_the_actionable_batch():
    for concept in (
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "LongTermDebtCurrent",
        "PaymentsForRepurchaseOfCommonStock",
    ):
        assert concept in PROPOSED_FIELD
