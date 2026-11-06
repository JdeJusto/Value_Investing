"""C1-M mapping gaps: IFRS splits, debt, EBIT fallback and net PPE variants.

Hermetic: feeds fact dictionaries to the normalizer, no database. The cases
come from the 30-ticker INSUFFICIENT_DATA audit (Sanofi, AstraZeneca, BTI,
TotalEnergies, JNJ, ADM, AT&T, AMT, APA).
"""

from __future__ import annotations

from datetime import date

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)


def _fact(concept, value, year=2025, end=None):
    return {
        "concept": concept,
        "value": value,
        "unit": "USD",
        "fiscal_year": year,
        "fiscal_period": "FY",
        "period_start": date(year, 1, 1),
        "period_end": end or date(year, 12, 31),
    }


def _normalize(facts):
    return FinancialDatabaseRepository()._normalize_financial_facts(facts)


def test_ifrs_current_split_and_net_ppe():
    """Sanofi/AstraZeneca file unprefixed IFRS concepts for the split and PPE."""
    data = _normalize(
        [
            _fact("CurrentAssets", 30_952_000_000),
            _fact("CurrentLiabilities", 28_345_000_000),
            _fact("PropertyPlantAndEquipment", 10_052_000_000),
        ]
    )["balance"]

    assert data["current_assets"] == 30_952_000_000
    assert data["current_liabilities"] == 28_345_000_000
    assert data["net_ppe"] == 10_052_000_000


def test_ifrs_borrowings_reconstruct_total_debt():
    """Current + non-current IFRS borrowings sum into total_debt."""
    data = _normalize(
        [
            _fact(
                "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
                3_590_000_000,
            ),
            _fact("LongtermBorrowings", 15_000_000_000),
        ]
    )["balance"]

    assert data["total_debt"] == 18_590_000_000


def test_tte_net_ppe_including_right_of_use_assets():
    """TotalEnergies FY2025 files only the ROU-inclusive net PP&E tag."""
    data = _normalize(
        [_fact("PropertyPlantAndEquipmentIncludingRightofuseAssets", 114_694_000_000)]
    )["balance"]

    assert data["net_ppe"] == 114_694_000_000


def test_us_net_ppe_after_accumulated_depreciation_variant():
    """AT&T/AMT/APA tag PP&E + finance-lease ROU after depreciation."""
    data = _normalize(
        [
            _fact(
                "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
                131_559_000_000,
            )
        ]
    )["balance"]

    assert data["net_ppe"] == 131_559_000_000


def test_ebit_fallback_from_pretax_and_interest():
    """JNJ/ADM stopped tagging operating income; EBIT = pretax + interest."""
    income = _normalize(
        [
            _fact(
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                1_255_000_000,
            ),
            _fact("InterestExpense", 612_000_000),
        ]
    )["income"]

    assert income["ebit"] == 1_867_000_000


def test_ebit_fallback_pretax_only_when_interest_missing():
    """No interest tag -> pretax income is the documented proxy."""
    income = _normalize(
        [
            _fact(
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                32_581_000_000,
            )
        ]
    )["income"]

    assert income["ebit"] == 32_581_000_000


def test_ebit_fallback_from_ifrs_accounting_profit_and_finance_costs():
    """TotalEnergies FY2025: AccountingProfit + FinanceCosts -> EBIT."""
    income = _normalize(
        [
            _fact("AccountingProfit", 22_449_000_000),
            _fact("FinanceCosts", 1_626_000_000),
        ]
    )["income"]

    assert income["pretax_income"] == 22_449_000_000
    assert income["interest_expense"] == 1_626_000_000
    assert income["ebit"] == 24_075_000_000


def test_operating_income_still_wins_over_the_fallback():
    """A filed operating-income line is never replaced by the derivation."""
    income = _normalize(
        [
            _fact("OperatingIncomeLoss", 5_000_000_000),
            _fact(
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                6_000_000_000,
            ),
            _fact("InterestExpense", 500_000_000),
        ]
    )["income"]

    assert income["ebit"] == 5_000_000_000


def test_verizon_network_capex_variant():
    """VZ tags network capex as PaymentsToAcquireOtherProductiveAssets."""
    cash = _normalize(
        [
            _fact(
                "PaymentsToAcquireOtherProductiveAssets",
                17_011_000_000,
                end=date(2025, 12, 31),
            )
        ]
    )["cash_flow"]

    assert cash["capital_expenditure"] == 17_011_000_000


def test_td_bank_dividends_ifrs_cash_flow_tag():
    """TD Bank files dividends under the IFRS financing-activities tag."""
    cash = _normalize(
        [
            _fact(
                "DividendsPaidClassifiedAsFinancingActivities",
                7_663_000_000,
                end=date(2025, 10, 31),
            )
        ]
    )["cash_flow"]

    assert cash["dividends_paid"] == 7_663_000_000
