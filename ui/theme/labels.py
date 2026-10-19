"""Human labels for financial statement lines.

Central map ``FIELD_LABELS``: XBRL concept -> English label. The Balance
T-view and the flat statement tables all resolve labels here so a concept
never shows its raw technical name (``cash_and_equivalents``) on screen.
Unknown concepts fall back to the English humanization from the read-only
backend view service (``humanize_concept``).
"""

from __future__ import annotations

from backend.services.financials_view_service import humanize_concept

#: XBRL concept -> English label.
FIELD_LABELS: dict[str, str] = {
    # --- Totals ---------------------------------------------------------
    "Assets": "Total assets",
    "AssetsTotal": "Total assets",
    "LiabilitiesAndStockholdersEquity": "Total liabilities and stockholders' equity",
    "Liabilities": "Total liabilities",
    "LiabilitiesTotal": "Total liabilities",
    # --- Subtotals (reported masses) ------------------------------------
    "AssetsCurrent": "Total current assets",
    "AssetsNoncurrent": "Total non-current assets",
    "LiabilitiesCurrent": "Total current liabilities",
    "LiabilitiesNoncurrent": "Total non-current liabilities",
    "StockholdersEquity": "Total stockholders' equity",
    "ShareholdersEquity": "Total shareholders' equity",
    "TotalEquityGrossMinorityInterest": "Total equity incl. minority interest",
    # --- Current assets -------------------------------------------------
    "CashAndCashEquivalentsAtCarryingValue": "Cash and cash equivalents",
    "CashAndCashEquivalents": "Cash and cash equivalents",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": (
        "Cash, cash equivalents and restricted cash"
    ),
    "ShortTermInvestments": "Short-term investments",
    "MarketableSecuritiesCurrent": "Marketable securities (current)",
    "AccountsReceivableNetCurrent": "Accounts receivable, net (current)",
    "AccountsReceivableNet": "Accounts receivable, net",
    "NontradeReceivablesCurrent": "Non-trade receivables (current)",
    "InventoryNet": "Inventory, net",
    "PrepaidExpenseAndOtherAssetsCurrent": "Prepaid expenses and other current assets",
    "OtherAssetsCurrent": "Other current assets",
    # --- Non-current assets ---------------------------------------------
    "PropertyPlantAndEquipmentNet": "Property, plant and equipment, net",
    "PropertyPlantAndEquipmentGross": "Property, plant and equipment, gross",
    "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment": (
        "Accumulated depreciation, depletion and amortization"
    ),
    "Goodwill": "Goodwill",
    "IntangibleAssetsNetExcludingGoodwill": "Intangible assets, net (excl. goodwill)",
    "FiniteLivedIntangibleAssetsNet": "Finite-lived intangible assets, net",
    "LongTermInvestments": "Long-term investments",
    "MarketableSecuritiesNoncurrent": "Marketable securities (non-current)",
    "DeferredTaxAssetsNoncurrent": "Deferred tax assets (non-current)",
    "OtherAssetsNoncurrent": "Other non-current assets",
    # --- Current liabilities --------------------------------------------
    "ShortTermBorrowings": "Short-term borrowings",
    "CommercialPaper": "Commercial paper",
    "DebtCurrent": "Debt (current)",
    "LongTermDebtCurrent": "Long-term debt (current portion)",
    "AccountsPayableCurrent": "Accounts payable (current)",
    "AccountsPayableAndAccruedLiabilitiesCurrent": "Accounts payable and accrued liabilities",
    "AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent": (
        "Accounts payable and accrued liabilities (current and non-current)"
    ),
    "AccountsPayableAndOtherAccruedLiabilities": (
        "Accounts payable and other accrued liabilities"
    ),
    "AccruedLiabilitiesCurrent": "Accrued liabilities (current)",
    "OtherLiabilitiesCurrent": "Other current liabilities",
    "ContractWithCustomerLiabilityCurrent": "Contract liabilities (current)",
    "DeferredRevenueCurrent": "Deferred revenue (current)",
    # --- Non-current liabilities ----------------------------------------
    "LongTermDebtNoncurrent": "Long-term debt (non-current)",
    "DebtNoncurrent": "Debt (non-current)",
    "LongTermLiabilities": "Long-term liabilities (total)",
    "LongTermDebt": "Long-term debt",
    "OperatingLeaseLiabilityNoncurrent": "Operating lease liabilities (non-current)",
    "FinanceLeaseLiabilityNoncurrent": "Finance lease liabilities (non-current)",
    "DeferredTaxLiabilitiesNoncurrent": "Deferred tax liabilities (non-current)",
    "DeferredTaxLiabilitiesNet": "Deferred tax liabilities, net",
    "OtherLiabilitiesNoncurrent": "Other non-current liabilities",
    # --- Equity ----------------------------------------------------------
    "PreferredStockValue": "Preferred stock",
    "CommonStockValue": "Common stock",
    "CommonStocksIncludingAdditionalPaidInCapital": (
        "Common stock incl. additional paid-in capital"
    ),
    "AdditionalPaidInCapital": "Additional paid-in capital",
    "PaidInCapital": "Paid-in capital",
    "RetainedEarningsAccumulatedDeficit": "Retained earnings (accumulated deficit)",
    "RetainedEarnings": "Retained earnings",
    "TreasuryStockValue": "Treasury stock",
    "AccumulatedOtherComprehensiveIncomeLossNetOfTax": (
        "Accumulated other comprehensive income (loss)"
    ),
    "MinorityInterest": "Minority interest",
    # --- Memoranda (non-monetary) ----------------------------------------
    "CommonStockSharesOutstanding": "Common shares outstanding",
    "CommonStockSharesIssued": "Common shares issued",
    "CommonStockSharesAuthorized": "Common shares authorized",
    "EntityCommonStockSharesOutstanding": "Entity common shares outstanding (cover)",
    "EntityPublicFloat": "Public float",
    "WeightedAverageNumberOfSharesOutstandingBasic": (
        "Weighted-average shares outstanding (basic)"
    ),
    "WeightedAverageNumberOfSharesOutstanding": "Weighted-average shares outstanding",
    "WeightedAverageNumberOfSharesOutstandingDiluted": (
        "Weighted-average shares outstanding (diluted)"
    ),
    "WeightedAverageNumberOfDilutedSharesOutstanding": (
        "Weighted-average diluted shares outstanding"
    ),
    "WeightedAverageNumberOfShareOutstandingBasicAndDiluted": (
        "Weighted-average shares outstanding (basic and diluted)"
    ),
    # --- Income statement ------------------------------------------------
    "Revenues": "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax": (
        "Revenue from contracts with customers (excl. assessed tax)"
    ),
    "CostOfGoodsAndServicesSold": "Cost of goods and services sold",
    "GrossProfit": "Gross profit",
    "SellingGeneralAndAdministrativeExpense": (
        "Selling, general and administrative expense"
    ),
    "OperatingIncomeLoss": "Operating income (loss)",
    "NonoperatingIncomeExpense": "Non-operating income (expense)",
    "IncomeTaxExpenseBenefit": "Income tax expense (benefit)",
    "NetIncomeLoss": "Net income (loss)",
    "ComprehensiveIncomeNetOfTax": "Comprehensive income, net of tax",
    "EarningsPerShareBasic": "Earnings per share, basic",
    "EarningsPerShareDiluted": "Earnings per share, diluted",
    "AmortizationMethodQualifiedAffordableHousingProjectInvestments": (
        "Amortization — qualified affordable housing project investments"
    ),
    "AmortizationMethodQualifiedAffordableHousingProjectInvestmentsAmortization": (
        "Amortization — qualified affordable housing investments (detail)"
    ),
    # --- Cash flow -------------------------------------------------------
    "NetCashProvidedByUsedInOperatingActivities": (
        "Net cash provided by (used in) operating activities"
    ),
    "NetCashProvidedByUsedInInvestingActivities": (
        "Net cash provided by (used in) investing activities"
    ),
    "NetCashProvidedByUsedInFinancingActivities": (
        "Net cash provided by (used in) financing activities"
    ),
    "DepreciationAmortizationAndAccretionNet": (
        "Depreciation, amortization and accretion, net"
    ),
    "PaymentsToAcquirePropertyPlantAndEquipment": (
        "Payments to acquire property, plant and equipment"
    ),
    "ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities": (
        "Proceeds from maturities of available-for-sale securities"
    ),
    "PaymentsForProceedsFromOtherInvestingActivities": (
        "Payments for / proceeds from other investing activities"
    ),
    "IncreaseDecreaseInAccountsReceivable": "Increase (decrease) in accounts receivable",
    "IncreaseDecreaseInInventories": "Increase (decrease) in inventories",
    "IncreaseDecreaseInAccountsPayable": "Increase (decrease) in accounts payable",
    "IncreaseDecreaseInOtherOperatingAssets": (
        "Increase (decrease) in other operating assets"
    ),
    "IncreaseDecreaseInOtherOperatingLiabilities": (
        "Increase (decrease) in other operating liabilities"
    ),
    "IncreaseDecreaseInDeposits": "Increase (decrease) in deposits",
    "IncreaseDecreaseInCashCollateralForBorrowedSecurities": (
        "Increase (decrease) in cash collateral for borrowed securities"
    ),
}


def label(concept: str) -> str:
    """Human label for a concept in English (falls back to humanization)."""
    return FIELD_LABELS.get(concept) or humanize_concept(concept)
