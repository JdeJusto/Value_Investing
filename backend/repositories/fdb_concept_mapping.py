"""XBRL concept mappings for Financial-DataBase facts.

Pure move out of ``financial_database_repository``: the curated concept to
field maps, the priority rankings, and the net-income convention helper. The
repository imports these names and re-exports them, so every existing import
path keeps working.
"""

from __future__ import annotations

# XBRL concepts carrying a stock-split conversion ratio (shares-after /
# shares-before per split, unit 'pure', period_end = effective split date).
# Used to reconstruct ``split_adjustment_factor`` on NormalizedFinancials so
# the methodologies stay hermetic (the factor is data, not a price lookup).
_SPLIT_RATIO_CONCEPTS = (
    "StockholdersEquityNoteStockSplitConversionRatio",
    "StockholdersEquityNoteStockSplitConversionRatio1",
)


# Concept mapping from Financial-DataBase XBRL concepts to Value Investing fields
# This maps common XBRL concepts to the financial statement fields we use
INCOME_STATEMENT_CONCEPTS = {
    # Revenue
    "Revenues": "revenue",
    "Revenue": "revenue",
    "RegulatedAndUnregulatedOperatingRevenue": "revenue",
    "SalesRevenueNet": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "RevenueFromContractWithCustomerIncludingAssessedTax": "revenue",
    # IFRS 15 tag used by 20-F/40-F filers (e.g. SOPHiA GENETICS); stored by
    # Financial-DataBase under the IFRS concept name.
    "RevenueFromContractsWithCustomers": "revenue",
    "SalesRevenueGoodsNet": "revenue",
    "SalesRevenueServicesNet": "revenue",
    # REITs file their rental income here when no 'Revenues' tag is present
    "OperatingLeaseLeaseIncome": "revenue",
    # Cost of Goods Sold
    "CostOfGoodsSold": "cogs",
    "CostOfRevenue": "cogs",
    "CostOfGoodsAndServicesSold": "cogs",
    # IFRS cost line used by 20-F/40-F filers.
    "CostOfSales": "cogs",
    # Gross Profit
    "GrossProfit": "gross_profit",
    # Operating Expenses
    "OperatingExpenses": "operating_expense",
    "ResearchAndDevelopmentExpense": "research_development",
    # JNJ files essentially all R&D under the ExcludingAcquiredInProcessCost
    # tag; its plain tag only carries a residual. The dominance override in
    # _normalize_financial_facts keeps the more complete figure.
    "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost": "research_development",
    "SellingGeneralAndAdministrativeExpense": "sga",
    # Operating Income
    "OperatingIncomeLoss": "operating_income",
    "OperatingIncome": "operating_income",
    # EBIT (rarely reported separately; filers of OperatingIncomeLoss get a
    # matching ebit via the fallback in _normalize_financial_facts)
    "EBIT": "ebit",
    # EBITDA
    "EBITDA": "ebitda",
    # Non-operating Income/Expense
    "NonoperatingIncomeExpense": "non_operating_income_expense",
    # Interest Expense
    "InterestExpense": "interest_expense",
    # Tax Provision
    "IncomeTaxExpenseBenefit": "tax_provision",
    "IncomeTaxExpense": "tax_provision",
    # Pretax Income
    "IncomeLossBeforeIncomeTaxes": "pretax_income",
    "PretaxIncome": "pretax_income",
    # Net Income
    "NetIncomeLossAvailableToCommonStockholdersBasic": "net_income",
    "NetIncomeLossAvailableToCommonStockholdersDiluted": "net_income",
    "NetIncomeLoss": "net_income",
    "NetIncome": "net_income",
    "ProfitLoss": "net_income",
    # Preferred dividends (income statement). The DDM subtracts them from the
    # total dividend base for financials whose only cash tag is the total
    # PaymentsOfDividends (JPM, C, GS, MS...); common-only tags are preferred
    # where they exist.
    "DividendsPreferredStock": "preferred_dividends",
    "DividendsPreferredStockCash": "preferred_dividends",
    "PreferredStockDividendsAndOtherAdjustments": "preferred_dividends",
}

# Some companies tag several elements with identical fiscal periods (e.g.
# RevenueFromContractWithCustomerExcludingAssessedTax for a single quarter vs
# Revenues for the full year, both with period_end=Dec-31). When several
# concepts map to the same field, prefer the most complete/representative one.
INCOME_FIELD_PRIORITY = {
    "revenue": [
        "Revenues",
        "Revenue",
        "RegulatedAndUnregulatedOperatingRevenue",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        # IFRS 15 revenue (20-F/40-F filers); after the US-GAAP tags so a
        # filer reporting both prefers the domestic tag.
        "RevenueFromContractsWithCustomers",
        # REIT rental income; ranked last so explicit revenue tags win, with a
        # value-based override in _normalize_financial_facts for REITs whose
        # rental income is the whole top line (e.g. CPT).
        "OperatingLeaseLeaseIncome",
    ],
    "net_income": [
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "NetIncomeLossAvailableToCommonStockholdersDiluted",
        "NetIncomeLoss",
        "NetIncome",
        "ProfitLoss",
    ],
}
INCOME_CONCEPT_RANK = {
    concept: rank
    for field, concepts in INCOME_FIELD_PRIORITY.items()
    for rank, concept in enumerate(concepts)
}

#: Net-income concepts and the convention they represent. "Available to
#: common" subtracts preferred dividends, so per-share metrics (EPS, P/E,
#: DDM) use it while the consolidated figure is the whole-company number.
_AVAILABLE_TO_COMMON_NET_INCOME = (
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "NetIncomeLossAvailableToCommonStockholdersDiluted",
)
_CONSOLIDATED_NET_INCOME = ("NetIncomeLoss", "NetIncome", "ProfitLoss")


def _income_convention(concept: str | None) -> str | None:
    """Label the net-income convention from the winning XBRL concept."""
    if concept in _AVAILABLE_TO_COMMON_NET_INCOME:
        return "available_to_common"
    if concept in _CONSOLIDATED_NET_INCOME:
        return "consolidated"
    return None


# Some companies file several capital-expenditure elements for the same period
# (e.g. AEP reports both PaymentsToAcquireProductiveAssets and the broader
# SegmentExpenditureAdditionToLongLivedAssets). Rank the concepts so the most
# complete figure wins instead of an arbitrary first-match.
CASH_FLOW_FIELD_PRIORITY = {
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "OperatingCashFlow",
        # Filers with discontinued operations (e.g. JCI after divesting its
        # residential HVAC business) tag OCF only under the continuing-
        # operations variant; the plain tag is preferred when both exist.
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capital_expenditure": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "SegmentExpenditureAdditionToLongLivedAssets",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForConstructionInProcess",
        "CapitalExpenditures",
        "CapitalExpenditure",
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        # Variant add-back tags used by utilities (AEE: ...AccretionNet) and
        # capital-intensive filers (PWR: Depreciation).
        "DepreciationAmortizationAndAccretionNet",
        "Depreciation",
        # Single-line-item (non-add-back) tags ranked last; only chosen when no
        # complete add-back tag exists.
        "UtilitiesOperatingExpenseDepreciationAndAmortization",
        "CostOfGoodsSoldDepreciationDepletionAndAmortization",
    ],
    "dividends_paid": [
        # Common-stock-specific tags first: USB/WFC file
        # PaymentsOfDividendsCommonStock, BAC files DividendsCommonStockCash;
        # the broader total-dividend tags (JPM's PaymentsOfDividends, the
        # ordinary-dividend variant) are fallbacks.
        "PaymentsOfDividendsCommonStock",
        "DividendsCommonStockCash",
        "PaymentsOfDividends",
        "PaymentsOfOrdinaryDividends",
        "DividendsPaid",
    ],
}
CASH_FLOW_CONCEPT_RANK = {
    concept: rank
    for field, concepts in CASH_FLOW_FIELD_PRIORITY.items()
    for rank, concept in enumerate(concepts)
}

# Total debt = current + non-current portion, each taken from the newest
# balance comparative. Companies file several interchangeable tags for the
# same portion (LongTermDebt / DebtNoncurrent / LongTermDebtNoncurrent for
# non-current; DebtCurrent / ShortTermBorrowings / CommercialPaper for
# current), so ONE concept per portion is preferred by priority: summing
# every distinct tag would double count aliases (e.g. Newmont reports
# LongTermDebt and LongTermDebtNoncurrent with the same value, and D reports
# LongTermDebt plus the overlapping LongTermDebtAndCapitalLeaseObligations).
DEBT_CURRENT_PRIORITY = [
    "DebtCurrent",
    "ShortTermBorrowings",
    "CommercialPaper",
    "LongTermDebtAndCapitalLeaseObligationsCurrent",
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
]
DEBT_NONCURRENT_PRIORITY = [
    "LongTermDebtAndCapitalLeaseObligations",
    "LongTermDebt",
    "DebtNoncurrent",
    "LongTermDebtNoncurrent",
    "LongTermNotesPayable",
    "SeniorNotes",
]
DEBT_CURRENT_RANK = {
    concept: rank for rank, concept in enumerate(DEBT_CURRENT_PRIORITY)
}
DEBT_NONCURRENT_RANK = {
    concept: rank for rank, concept in enumerate(DEBT_NONCURRENT_PRIORITY)
}

BALANCE_SHEET_CONCEPTS = {
    # Total Assets
    "Assets": "total_assets",
    "AssetsTotal": "total_assets",
    # Current Assets
    "AssetsCurrent": "current_assets",
    "CashAndCashEquivalentsAtCarryingValue": "cash_and_equivalents",
    "CashAndCashEquivalents": "cash_and_equivalents",
    "AccountsReceivableNetCurrent": "accounts_receivable",
    "InventoryNet": "inventory",
    # Total Liabilities
    "Liabilities": "total_liabilities",
    "LiabilitiesTotal": "total_liabilities",
    # Current Liabilities
    "LiabilitiesCurrent": "current_liabilities",
    "AccountsPayableCurrent": "accounts_payable",
    # Long Term Liabilities
    "LongTermLiabilities": "long_term_liabilities",
    # Total Debt (approximation)
    "DebtCurrent": "total_debt",
    "DebtNoncurrent": "total_debt",
    "LongTermDebt": "total_debt",
    "LongTermDebtNoncurrent": "total_debt",
    # Cash and Equivalents
    "CashAndCashEquivalentsAtCarryingValue": "cash_and_equivalents",  # noqa: F601 — XBRL alias of the pair above
    "CashAndCashEquivalents": "cash_and_equivalents",  # noqa: F601 — XBRL alias of the pair above
    # Asset managers/others that report only the restricted-inclusive total
    # (e.g. BEN: CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents)
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": "cash_and_equivalents",
    # Net property, plant and equipment (Greenblatt's ROC denominator)
    "PropertyPlantAndEquipmentNet": "net_ppe",
    # Working Capital (calculated as Current Assets - Current Liabilities)
    # We'll calculate this separately since it's not typically stored directly
    # Retained Earnings
    "RetainedEarningsAccumulatedDeficit": "retained_earnings",
    "RetainedEarnings": "retained_earnings",
    # Stockholders Equity
    "StockholdersEquity": "stockholders_equity",
    "TotalEquityGrossMinorityInterest": "stockholders_equity",
    "ShareholdersEquity": "stockholders_equity",
    # Shares Outstanding
    "WeightedAverageNumberOfSharesOutstandingBasic": "shares_outstanding",
    "WeightedAverageNumberOfSharesOutstanding": "shares_outstanding",
    "WeightedAverageNumberOfSharesOutstandingDiluted": "shares_outstanding",
    # Point-in-time share counts (cover page / balance sheet). Financial-DataBase
    # stores these for most filers, and they are the only per-year share count
    # that survives when the weighted-average concepts are absent — without
    # them the P/E and P/BV criteria could never be evaluated.
    "CommonStockSharesOutstanding": "shares_outstanding",
    "EntityCommonStockSharesOutstanding": "shares_outstanding",
}

CASH_FLOW_CONCEPTS = {
    # Operating Cash Flow
    "NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
    "OperatingCashFlow": "operating_cash_flow",
    # see CASH_FLOW_FIELD_PRIORITY['operating_cash_flow']
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": "operating_cash_flow",
    # Capital Expenditure (positive value)
    "PaymentsToAcquireProductiveAssets": "capital_expenditure",
    "PaymentsToAcquirePropertyPlantAndEquipment": "capital_expenditure",
    "SegmentExpenditureAdditionToLongLivedAssets": "capital_expenditure",
    "PaymentsForConstructionInProcess": "capital_expenditure",
    "CapitalExpenditures": "capital_expenditure",
    "CapitalExpenditure": "capital_expenditure",
    # Free Cash Flow (we'll calculate this as Operating CF - CapEx)
    # Depreciation and Amortization
    "DepreciationDepletionAndAmortization": "depreciation_amortization",
    "DepreciationAndAmortization": "depreciation_amortization",
    # Utilities/multi-entity filers use variant tags for the D&A add-back
    "DepreciationAmortizationAndAccretionNet": "depreciation_amortization",
    "Depreciation": "depreciation_amortization",
    "UtilitiesOperatingExpenseDepreciationAndAmortization": "depreciation_amortization",
    "CostOfGoodsSoldDepreciationDepletionAndAmortization": "depreciation_amortization",
    # Dividends Paid
    "PaymentsOfDividendsCommonStock": "dividends_paid",
    "DividendsCommonStockCash": "dividends_paid",
    "PaymentsOfDividends": "dividends_paid",
    "PaymentsOfOrdinaryDividends": "dividends_paid",
    "DividendsPaid": "dividends_paid",
    # Repurchase of Stock
    "PaymentsForRepurchaseOfEquity": "repurchase_of_stock",
    "RepurchaseOfCommonStock": "repurchase_of_stock",
    # Working Capital Change (we'll calculate this)
}


CORE_STATEMENT_CONCEPTS = sorted(
    set(INCOME_STATEMENT_CONCEPTS)
    | set(BALANCE_SHEET_CONCEPTS)
    | set(CASH_FLOW_CONCEPTS)
)


#: Cash dividend tags that already exclude preferred dividends; when one of
#: these wins for ``dividends_paid`` the income-statement preferred figure
#: must not be subtracted again by the DDM.
_COMMON_ONLY_DIVIDEND_CONCEPTS = frozenset(
    {"PaymentsOfDividendsCommonStock", "DividendsCommonStockCash"}
)
