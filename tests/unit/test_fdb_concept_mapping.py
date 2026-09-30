"""Hermetic tests for the FDB alternative-concept mapping.

No database, no network: these exercise the pure builder
``_normalize_financial_facts`` with in-memory fact dicts (same pattern as
``test_fdb_split_and_income_fields``).

Covers the mapping added for XOM / GM / T:

* gross_profit falls back to the standard ``revenue - cogs`` identity when the
  ``GrossProfit`` tag is absent (GM stopped tagging it after FY2012; T after
  the 2023 restatement — their cost lines remain tagged for earlier years);
* a filed ``GrossProfit`` tag is never overridden by the derivation;
* the derivation needs both revenue and a cost-of-revenue line, so a filer
  that reports neither (XOM) stays without gross data instead of getting a
  fabricated figure.
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


def _income(*facts):
    return FinancialDatabaseRepository()._normalize_financial_facts(list(facts))[
        "income"
    ]


def test_gross_profit_derived_when_tag_absent():
    """Revenues - CostOfRevenue fills gross_profit when no tag is filed."""
    income = _income(
        _fact("Revenues", 1_000_000_000),
        _fact("CostOfRevenue", 600_000_000),
    )
    assert income["gross_profit"] == 400_000_000


def test_filed_gross_profit_tag_never_overridden():
    """A filed GrossProfit is authoritative; the derivation must not fire."""
    income = _income(
        _fact("Revenues", 1_000_000_000),
        _fact("CostOfRevenue", 600_000_000),
        _fact("GrossProfit", 999_000_000),
    )
    assert income["gross_profit"] == 999_000_000


def test_no_derivation_without_cost_line():
    """No cogs tag -> no derived gross (avoids fabricating data)."""
    income = _income(_fact("Revenues", 1_000_000_000))
    assert income.get("gross_profit") is None


def test_no_derivation_without_revenue():
    """No revenue -> no derived gross."""
    income = _income(_fact("CostOfRevenue", 600_000_000))
    assert income.get("gross_profit") is None


def test_cogs_alternative_tags_map_and_derive():
    """Each mapped cost-of-revenue tag feeds cogs and the derivation."""
    for cogs_tag in (
        "CostOfGoodsSold",
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
    ):
        income = _income(
            _fact("Revenues", 170_000_000_000),
            _fact(cogs_tag, 145_000_000_000),
        )
        assert income["cogs"] == 145_000_000_000, cogs_tag
        assert income["gross_profit"] == 25_000_000_000, cogs_tag


def test_gm_style_year_keeps_other_income_fields():
    """GM-style bucket: derived gross coexists with filing-level margins."""
    income = _income(
        _fact("Revenues", 171_842_000_000),
        _fact("CostOfGoodsAndServicesSold", 146_751_000_000),
        _fact("OperatingIncomeLoss", 10_335_000_000),
        _fact("NetIncomeLoss", 9_010_000_000),
    )
    assert income["cogs"] == 146_751_000_000
    assert income["gross_profit"] == 171_842_000_000 - 146_751_000_000
    assert income["operating_income"] == 10_335_000_000
    assert income["net_income"] == 9_010_000_000


def test_t_style_year_derives_gross_margin():
    """T-style bucket: CostOfRevenue carries the cost line for the margin."""
    income = _income(
        _fact("Revenues", 122_428_000_000),
        _fact("CostOfRevenue", 75_130_000_000),
    )
    assert income["gross_profit"] == 122_428_000_000 - 75_130_000_000


def test_preferred_dividend_tag_maps_to_preferred_dividends():
    """JPM/C/GS/MS file preferred dividends under DividendsPreferredStock."""
    income = _income(_fact("DividendsPreferredStock", 1_600_000_000))
    assert income["preferred_dividends"] == 1_600_000_000


def test_preferred_dividend_alternative_tag_maps():
    income = _income(_fact("PreferredStockDividendsAndOtherAdjustments", 900_000_000))
    assert income["preferred_dividends"] == 900_000_000


def test_common_only_dividend_tag_suppresses_preferred():
    # WFC/USB file PaymentsOfDividendsCommonStock (already common-only) plus
    # a preferred tag: the preferred figure must not be kept for subtraction.
    normalized = FinancialDatabaseRepository()._normalize_financial_facts(
        [
            _fact("PaymentsOfDividendsCommonStock", 5_000_000_000),
            _fact("DividendsPreferredStockCash", 1_000_000_000),
        ]
    )
    assert normalized["income"]["preferred_dividends"] is None
    assert normalized["cash_flow"]["dividends_paid"] == 5_000_000_000


def test_total_dividend_tag_keeps_preferred():
    normalized = FinancialDatabaseRepository()._normalize_financial_facts(
        [
            _fact("PaymentsOfDividends", 16_000_000_000),
            _fact("DividendsPreferredStock", 1_600_000_000),
        ]
    )
    assert normalized["income"]["preferred_dividends"] == 1_600_000_000
    assert normalized["cash_flow"]["dividends_paid"] == 16_000_000_000


def test_ifrs_revenue_from_contracts_maps():
    """IFRS 15 revenue (20-F/40-F filers) maps to revenue."""
    income = _income(_fact("RevenueFromContractsWithCustomers", 900.0))
    assert income["revenue"] == 900.0


def test_ifrs_cost_of_sales_maps_and_derives_gross_profit():
    """IFRS CostOfSales maps to cogs and feeds the gross-profit identity."""
    income = _income(
        _fact("RevenueFromContractsWithCustomers", 900.0),
        _fact("CostOfSales", 400.0),
    )
    assert income["revenue"] == 900.0
    assert income["cogs"] == 400.0
    assert income["gross_profit"] == 500.0


def test_us_gaap_revenue_wins_over_ifrs_when_both_present():
    """A filer reporting both taxonomies prefers the US-GAAP tag."""
    income = _income(
        _fact("Revenues", 1000.0),
        _fact("RevenueFromContractsWithCustomers", 900.0),
    )
    assert income["revenue"] == 1000.0
