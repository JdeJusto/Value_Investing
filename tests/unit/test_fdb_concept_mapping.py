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


# ---------------------------------------------------------------------------
# REIT / structural concept gaps (COLD case)
# ---------------------------------------------------------------------------
def test_pretax_income_continuing_operations_concept_maps():
    """The standard US-GAAP pretax line (COLD and most filers) maps."""
    income = _income(
        _fact(
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
            "ExtraordinaryItemsNoncontrollingInterest",
            -135_733_000,
        )
    )
    assert income["pretax_income"] == -135_733_000


def test_interest_expense_nonoperating_maps_as_fallback():
    """REITs file InterestExpenseNonoperating when the plain tag is absent."""
    income = _income(_fact("InterestExpenseNonoperating", 147_776_000))
    assert income["interest_expense"] == 147_776_000


def test_plain_interest_expense_wins_over_nonoperating():
    income = _income(
        _fact("InterestExpense", 100.0),
        _fact("InterestExpenseNonoperating", 90.0),
    )
    assert income["interest_expense"] == 100.0


def test_reit_rental_revenue_aliases_map():
    """OperatingLeaseIncome / RentalRevenue / RealEstateRevenueNet -> revenue."""
    for tag in ("OperatingLeaseIncome", "RentalRevenue", "RealEstateRevenueNet"):
        income = _income(_fact(tag, 500.0))
        assert income["revenue"] == 500.0, tag


def test_costs_and_expenses_maps_to_operating_expense():
    """REIT total operating costs line fills operating_expense when filed alone."""
    income = _income(_fact("CostsAndExpenses", 2_594_612_000))
    assert income["operating_expense"] == 2_594_612_000


def test_operating_expenses_wins_over_costs_and_expenses():
    income = _income(
        _fact("OperatingExpenses", 100.0),
        _fact("CostsAndExpenses", 90.0),
    )
    assert income["operating_expense"] == 100.0


def test_secured_debt_maps_to_total_debt():
    """REIT mortgage/secured debt (COLD) fills total_debt when nothing else exists."""
    normalized = FinancialDatabaseRepository()._normalize_financial_facts(
        [_fact("SecuredDebt", 3_792_123_000)]
    )
    assert normalized["balance"]["total_debt"] == 3_792_123_000


def test_long_term_debt_wins_over_secured_debt():
    normalized = FinancialDatabaseRepository()._normalize_financial_facts(
        [
            _fact("LongTermDebt", 4_140_235_000),
            _fact("SecuredDebt", 3_792_123_000),
        ]
    )
    assert normalized["balance"]["total_debt"] == 4_140_235_000


# ---------------------------------------------------------------------------
# Systematic coverage batch: banks, unclassified balance sheets, fallbacks
# ---------------------------------------------------------------------------
def test_bank_gross_interest_plus_noninterest_reconstructs_revenue():
    income = _income(
        _fact("InterestIncomeOperating", 100_000),
        _fact("InterestExpense", 40_000),
        _fact("NoninterestIncome", 30_000),
    )
    assert income["revenue"] == 90_000


def test_bank_net_interest_pair_reconstructs_revenue():
    income = _income(
        _fact("InterestIncomeExpenseNet", 60_000),
        _fact("NoninterestIncome", 30_000),
    )
    assert income["revenue"] == 90_000


def test_net_ppe_derived_from_gross_minus_accumulated():
    normalized = FinancialDatabaseRepository()._normalize_financial_facts(
        [
            _fact("PropertyPlantAndEquipmentGross", 1_000_000),
            _fact(
                "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
                400_000,
            ),
        ]
    )
    derived = FinancialDatabaseRepository()._calculate_derived_fields(normalized)
    assert derived["balance"]["net_ppe"] == 600_000


def test_filed_net_ppe_is_not_overridden():
    normalized = FinancialDatabaseRepository()._normalize_financial_facts(
        [
            _fact("PropertyPlantAndEquipmentNet", 500_000),
            _fact("PropertyPlantAndEquipmentGross", 1_000_000),
            _fact(
                "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
                400_000,
            ),
        ]
    )
    derived = FinancialDatabaseRepository()._calculate_derived_fields(normalized)
    assert derived["balance"]["net_ppe"] == 500_000


def test_diluted_shares_word_order_tag_maps():
    normalized = FinancialDatabaseRepository()._normalize_financial_facts(
        [_fact("WeightedAverageNumberOfDilutedSharesOutstanding", 123_000)]
    )
    assert normalized["balance"]["shares_outstanding"] == 123_000


def test_liabilities_and_equity_maps_to_total_assets():
    normalized = FinancialDatabaseRepository()._normalize_financial_facts(
        [_fact("LiabilitiesAndStockholdersEquity", 500_000)]
    )
    assert normalized["balance"]["total_assets"] == 500_000


def test_unclassified_balance_sheet_receivable_and_payable_map():
    normalized = FinancialDatabaseRepository()._normalize_financial_facts(
        [
            _fact("AccountsReceivableNet", 100_000),
            _fact("AccountsPayableAndAccruedLiabilitiesCurrent", 80_000),
        ]
    )
    assert normalized["balance"]["accounts_receivable"] == 100_000
    assert normalized["balance"]["accounts_payable"] == 80_000


def test_long_term_debt_current_counts_toward_total_debt():
    normalized = FinancialDatabaseRepository()._normalize_financial_facts(
        [_fact("LongTermDebtCurrent", 50_000)]
    )
    assert normalized["balance"]["total_debt"] == 50_000


def test_repurchase_fallback_tags_map():
    for tag in (
        "PaymentsForRepurchaseOfCommonStock",
        "StockRepurchasedDuringPeriodValue",
    ):
        normalized = FinancialDatabaseRepository()._normalize_financial_facts(
            [_fact(tag, 10_000)]
        )
        assert normalized["cash_flow"]["repurchase_of_stock"] == 10_000, tag


def test_general_and_administrative_fills_sga_when_absent():
    income = _income(_fact("GeneralAndAdministrativeExpense", 100))
    assert income["sga"] == 100


def test_sga_wins_over_general_and_administrative():
    income = _income(
        _fact("SellingGeneralAndAdministrativeExpense", 120),
        _fact("GeneralAndAdministrativeExpense", 100),
    )
    assert income["sga"] == 120


def test_other_nonoperating_maps_and_broader_tag_wins():
    income = _income(_fact("OtherNonoperatingIncomeExpense", 50))
    assert income["non_operating_income_expense"] == 50
    income = _income(
        _fact("NonoperatingIncomeExpense", 70),
        _fact("OtherNonoperatingIncomeExpense", 50),
    )
    assert income["non_operating_income_expense"] == 70


def test_pretax_minority_variant_maps():
    income = _income(
        _fact(
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterest"
            "AndIncomeLossFromEquityMethodInvestments",
            -100,
        )
    )
    assert income["pretax_income"] == -100


def test_continuing_operations_net_income_fallback():
    income = _income(_fact("IncomeLossFromContinuingOperations", 100))
    assert income["net_income"] == 100
    income = _income(
        _fact("NetIncomeLoss", 90),
        _fact("IncomeLossFromContinuingOperations", 100),
    )
    assert income["net_income"] == 90
