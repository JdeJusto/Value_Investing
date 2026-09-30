"""Regression tests: revenue reconstruction for REITs and banks/brokers in
``_normalize_financial_facts`` (no database required — pure mapping logic).

Covers the edge cases that used to be mishandled:
- a small side rental must never shadow a genuine contract-revenue figure,
- the bank pair must only reconstruct revenue when it *dominates* whatever
  revenue tag was picked (a larger filed `Revenues` must not be clobbered),
- a single bank component alone never triggers the reconstruction,
- a non-positive bank pair is never reported as revenue.
"""

from datetime import date

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)


def _fact(concept, value, year=2024, period="FY", end=None):
    return {
        "concept": concept,
        "value": value,
        "unit": "USD",
        "fiscal_year": year,
        "fiscal_period": period,
        "period_start": date(year, 1, 1),
        "period_end": end or date(year, 12, 31),
    }


def _revenue(facts):
    return (
        FinancialDatabaseRepository()
        ._normalize_financial_facts(facts)["income"]
        .get("revenue")
    )


def test_reit_rental_income_overrides_small_contract_revenue():
    """CPT case: 1.57B rental vs a tiny 13M contract tag -> rental wins."""
    facts = [
        _fact("RevenueFromContractWithCustomerExcludingAssessedTax", 13_000_000),
        _fact("OperatingLeaseLeaseIncome", 1_574_000_000),
    ]
    assert _revenue(facts) == 1_574_000_000


def test_reit_rental_income_used_when_no_revenue_tag():
    """A pure REIT files only OperatingLeaseLeaseIncome -> it is the top line."""
    facts = [_fact("OperatingLeaseLeaseIncome", 1_574_000_000)]
    assert _revenue(facts) == 1_574_000_000


def test_small_rental_never_shadows_real_revenue():
    """DD case: 6.85B sales vs a 74M side rental -> sales stay."""
    facts = [
        _fact("SalesRevenueNet", 6_849_000_000),
        _fact("OperatingLeaseLeaseIncome", 74_000_000),
    ]
    assert _revenue(facts) == 6_849_000_000


def test_bank_pair_reconstructs_net_top_line():
    """RJF/MTB/WFC-style filers with no Revenues element: interest + non-interest."""
    facts = [
        _fact("InterestIncomeExpenseNet", 7_500_000_000),
        _fact("NoninterestIncome", 1_517_000_000),
    ]
    assert _revenue(facts) == 9_017_000_000


def test_bank_pair_requires_both_components():
    """A single component alone never triggers the reconstruction."""
    facts = [
        _fact("InterestIncomeExpenseNet", 7_500_000_000),
        _fact("SalesRevenueNet", 100_000_000),
    ]
    assert _revenue(facts) == 100_000_000


def test_bank_pair_never_clobbers_larger_filed_revenue():
    """A financial holding company that files a genuine, larger Revenues tag
    keeps it — an incidental small interest + non-interest pair must not
    replace real sales (this used to overwrite unconditionally)."""
    facts = [
        _fact("Revenues", 1_000_000_000),
        _fact("InterestIncomeExpenseNet", 5_000_000),
        _fact("NoninterestIncome", 2_000_000),
    ]
    assert _revenue(facts) == 1_000_000_000


def test_bank_pair_with_negative_total_never_reported_as_revenue():
    """A rate-spike year where net interest plus fees is negative must not
    produce a negative revenue line."""
    facts = [
        _fact("InterestIncomeExpenseNet", -3_000_000_000),
        _fact("NoninterestIncome", 1_000_000_000),
    ]
    assert _revenue(facts) is None


def test_non_positive_rental_never_replaces_real_revenue():
    facts = [
        _fact("Revenues", 500_000_000),
        _fact("OperatingLeaseLeaseIncome", -10_000_000),
    ]
    assert _revenue(facts) == 500_000_000
