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
    "CashAndDueFromBanks": "Cash and due from banks",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": (
        "Cash, cash equivalents and restricted cash"
    ),
    "InterestBearingDepositsInBanks": "Deposits with banks",
    "ShortTermInvestments": "Short-term investments",
    "MarketableSecuritiesCurrent": "Marketable securities (current)",
    "ReceivablesNetCurrent": "Receivables, net (current)",
    "AccountsReceivableNetCurrent": "Accounts receivable, net (current)",
    "AccountsReceivableNet": "Accounts receivable, net",
    "AccountsAndOtherReceivablesNetCurrent": "Accounts and other receivables, net",
    "PremiumsAndOtherReceivablesNet": "Premiums and other receivables, net",
    "PremiumsReceivableAtCarryingValue": "Premiums receivable, at carrying value",
    "NotesReceivableNet": "Notes receivable, net",
    "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss": (
        "Financing receivables, net"
    ),
    "NontradeReceivablesCurrent": "Non-trade receivables (current)",
    "FederalFundsSoldAndSecuritiesPurchasedUnderAgreementsToResell": (
        "Federal funds sold and securities purchased under agreements to resell"
    ),
    "SecuritiesPurchasedUnderAgreementsToResell": (
        "Securities purchased under agreements to resell"
    ),
    "InventoryNet": "Inventory, net",
    "EnergyRelatedInventory": "Inventory — energy related",
    "InventoryPartsAndComponentsNetOfReserves": "Inventory — materials and supplies, net",
    "PrepaidExpenseAndOtherAssetsCurrent": "Prepaid expenses and other current assets",
    "OtherAssetsCurrent": "Other current assets",
    # --- Non-current assets ---------------------------------------------
    "PropertyPlantAndEquipmentNet": "Property, plant and equipment, net",
    "PropertyPlantAndEquipmentGross": "Property, plant and equipment, gross",
    "CapitalizedCostsOilAndGasProducingActivitiesNet": (
        "Property, plant and equipment, net (oil & gas)"
    ),
    "CapitalizedCostsOilAndGasProducingActivitiesGross": (
        "Property, plant and equipment, gross (oil & gas)"
    ),
    "CapitalizedCostsAccumulatedDepreciationDepletionAmortizationAndValuationAllowanceForRelatingToOilAndGasProducingActivities": (
        "Accumulated depreciation, depletion and amortization (oil & gas)"
    ),
    "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment": (
        "Accumulated depreciation, depletion and amortization"
    ),
    "Goodwill": "Goodwill",
    "IntangibleAssetsNetExcludingGoodwill": "Intangible assets, net (excl. goodwill)",
    "FiniteLivedIntangibleAssetsNet": "Finite-lived intangible assets, net",
    "IndefiniteLivedIntangibleAssetsExcludingGoodwill": (
        "Indefinite-lived intangible assets (excl. goodwill)"
    ),
    "OtherIntangibleAssetsNet": "Other intangible assets, net",
    "LongTermInvestments": "Long-term investments",
    "LongTermInvestmentsAndReceivablesNet": "Long-term investments and receivables, net",
    "Investments": "Investments",
    "MarketableSecurities": "Marketable securities",
    "MarketableSecuritiesNoncurrent": "Marketable securities (non-current)",
    "EquitySecuritiesFvNi": "Equity securities at fair value through income",
    "EquitySecuritiesFvNiCurrentAndNoncurrent": (
        "Equity securities at fair value through income (current and non-current)"
    ),
    "AvailableForSaleSecuritiesDebtSecurities": "Available-for-sale debt securities",
    "DebtSecuritiesAvailableForSaleExcludingAccruedInterest": (
        "Available-for-sale securities, net"
    ),
    "OtherInvestments": "Other investments",
    "EquityMethodInvestments": "Equity method investments",
    "InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures": (
        "Investments in affiliates, subsidiaries, associates and joint ventures"
    ),
    "DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss": (
        "Held-to-maturity securities, net"
    ),
    "DebtSecuritiesHeldToMaturityExcludingAccruedInterestBeforeAllowanceForCreditLoss": (
        "Held-to-maturity securities, gross"
    ),
    "SecuritiesBorrowed": "Securities borrowed",
    "SeparateAccountAssets": "Separate account assets",
    "MarketRiskBenefitAssetAmount": "Market risk benefits (asset)",
    "AssetsHeldByInsuranceRegulators": "Assets held by insurance regulators",
    "RegulatoryAssetsNoncurrent": "Regulatory assets (non-current)",
    "RegulatedEntityOtherAssetsNoncurrent": "Other assets of regulated entities",
    "DeferredPolicyAcquisitionCosts": "Deferred policy acquisition costs",
    "ReinsuranceRecoverables": "Reinsurance receivables",
    "ReinsuranceRecoverablesGross": "Reinsurance receivables, gross",
    "ReinsuranceRecoverableForUnpaidClaimsAndClaimsAdjustments": (
        "Reinsurance recoverable for unpaid claims and claim adjustments"
    ),
    "ReinsuranceRecoverablesOnPaidAndUnpaidLosses": (
        "Reinsurance receivables on paid and unpaid losses"
    ),
    "DeferredRentReceivablesNet": "Deferred rent receivables, net",
    "DeferredRentReceivablesNetNoncurrent": "Deferred rent receivables (non-current)",
    "OperatingLeaseRightOfUseAsset": "Operating lease right-of-use assets",
    "DeferredTaxAssetsNoncurrent": "Deferred tax assets (non-current)",
    "DeferredTaxAssetsNet": "Deferred tax assets, net",
    "DeferredIncomeTaxAssetsNet": "Deferred tax assets, net",
    "DeferredIncomeTaxesAndOtherAssetsNoncurrent": "Deferred income taxes and other assets",
    "OtherAssetsNoncurrent": "Other non-current assets",
    "OtherAssets": "Other assets",
    "OtherAssetsMiscellaneous": "Other assets (miscellaneous)",
    "OtherAssetsMiscellaneousNoncurrent": "Other non-current assets (miscellaneous)",
    "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization": (
        "Property, plant and equipment and finance lease right-of-use assets, net"
    ),
    "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetBeforeAccumulatedDepreciationAndAmortization": (
        "Property, plant and equipment and finance lease right-of-use assets, gross"
    ),
    "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAccumulatedDepreciationAndAmortization": (
        "Accumulated depreciation and amortization (PP&E and finance leases)"
    ),
    "PublicUtilitiesPropertyPlantAndEquipmentNet": (
        "Public utilities property, plant and equipment, net"
    ),
    "PublicUtilitiesPropertyPlantAndEquipmentPlantInService": (
        "Public utilities property, plant and equipment, plant in service"
    ),
    "PublicUtilitiesPropertyPlantAndEquipmentAccumulatedDepreciation": (
        "Accumulated depreciation (public utilities property, plant and equipment)"
    ),
    "RealEstateInvestmentPropertyNet": "Real estate investment property, net",
    "RealEstateGrossAtCarryingValue": "Real estate, gross",
    "RealEstateAccumulatedDepreciation": "Accumulated depreciation (real estate)",
    "RealEstateInvestmentPropertyAccumulatedDepreciation": (
        "Accumulated depreciation (real estate investment property)"
    ),
    "OilAndGasPropertySuccessfulEffortMethodGross": (
        "Oil & gas property (successful effort method), gross"
    ),
    # --- Current liabilities --------------------------------------------
    "ShortTermBorrowings": "Short-term borrowings",
    "CommercialPaper": "Commercial paper",
    "DebtCurrent": "Debt (current)",
    "LongTermDebtCurrent": "Long-term debt (current portion)",
    "AccountsPayableCurrent": "Accounts payable (current)",
    "AccountsPayableTradeCurrent": "Trade accounts payable (current)",
    "AccountsPayableOtherCurrent": "Other accounts payable (current)",
    "AccountsPayableCurrentAndNoncurrent": "Accounts payable (current and non-current)",
    "AccountsPayableAndAccruedLiabilitiesCurrent": "Accounts payable and accrued liabilities",
    "AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent": (
        "Accounts payable and accrued liabilities (current and non-current)"
    ),
    "AccountsPayableAndOtherAccruedLiabilities": (
        "Accounts payable and other accrued liabilities"
    ),
    "AccruedLiabilitiesCurrent": "Accrued liabilities (current)",
    "AccruedLiabilitiesAndOtherLiabilities": "Accrued and other liabilities",
    "OtherAccruedLiabilitiesCurrent": "Other accrued liabilities (current)",
    "EmployeeRelatedLiabilitiesCurrent": "Employee-related liabilities (current)",
    "StandardProductWarrantyAccrual": "Warranty accrual (current)",
    "OtherLiabilitiesCurrent": "Other current liabilities",
    "AccruedIncomeTaxesCurrent": "Income taxes payable (current)",
    "TaxesPayableCurrent": "Income taxes payable (current)",
    "InterestPayableCurrent": "Interest payable (current)",
    "FederalFundsPurchasedAndSecuritiesSoldUnderAgreementsToRepurchase": (
        "Federal funds purchased and securities sold under agreements to repurchase"
    ),
    "DividendsPayableCurrentAndNoncurrent": "Dividends payable",
    "DividendsPayableNoncurrent": "Dividends payable (non-current)",
    "ContractWithCustomerLiabilityCurrent": "Contract liabilities (current)",
    "ContractWithCustomerLiability": "Contract liabilities",
    "DeferredRevenueCurrent": "Deferred revenue (current)",
    "DividendsPayableCurrent": "Dividends payable (current)",
    "LongTermDebtAndCapitalLeaseObligationsCurrent": (
        "Long-term debt and finance lease obligations (current portion)"
    ),
    "OtherShortTermBorrowings": "Other short-term borrowings",
    "UnearnedPremiums": "Unearned premiums",
    "SupplementaryInsuranceInformationUnearnedPremiums": (
        "Unearned premiums (insurance information)"
    ),
    "PolicyholderContractDeposits": "Policyholder contract deposits",
    "PolicyholderFunds": "Policyholder funds",
    "Deposits": "Deposits",
    "InterestBearingDepositLiabilities": "Interest-bearing deposits",
    "NoninterestBearingDepositLiabilities": "Non-interest-bearing deposits",
    "DepositsDomestic": "Domestic deposits",
    "InterestBearingDepositLiabilitiesDomestic": "Domestic interest-bearing deposits",
    "NoninterestBearingDepositLiabilitiesDomestic": (
        "Domestic non-interest-bearing deposits"
    ),
    "DemandDepositAccounts": "Demand deposit accounts",
    "DepositsSavingsDeposits": "Savings deposits",
    "DepositsMoneyMarketDeposits": "Money market deposits",
    "TimeDeposits": "Time deposits",
    "SecuritiesSoldUnderAgreementsToRepurchase": (
        "Securities sold under agreements to repurchase"
    ),
    "TradingLiabilities": "Trading liabilities",
    # --- Non-current liabilities ----------------------------------------
    "LongTermDebtNoncurrent": "Long-term debt (non-current)",
    "DebtNoncurrent": "Debt (non-current)",
    "LongTermLiabilities": "Long-term liabilities (total)",
    "LongTermDebt": "Long-term debt",
    "LongTermDebtAndCapitalLeaseObligations": (
        "Long-term debt and finance lease obligations"
    ),
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities": (
        "Long-term debt and finance lease obligations (incl. current maturities)"
    ),
    "LongTermNotesPayable": "Long-term notes payable",
    "SeniorLongTermNotes": "Senior long-term notes",
    "UnsecuredDebt": "Unsecured debt",
    "DebtAndCapitalLeaseObligations": "Debt and finance lease obligations",
    "LiabilitiesOtherThanLongtermDebtNoncurrent": (
        "Other liabilities (excluding long-term debt)"
    ),
    "RegulatoryLiabilityNoncurrent": "Regulatory liabilities (non-current)",
    "RegulatoryLiabilities": "Regulatory liabilities",
    "OperatingLeaseLiabilityNoncurrent": "Operating lease liabilities (non-current)",
    "OperatingLeaseLiability": "Operating lease liabilities",
    "FinanceLeaseLiabilityNoncurrent": "Finance lease liabilities (non-current)",
    "FinanceLeaseLiability": "Finance lease liabilities",
    "DeferredTaxLiabilitiesNoncurrent": "Deferred tax liabilities (non-current)",
    "DeferredTaxLiabilitiesNet": "Deferred tax liabilities, net",
    "DeferredIncomeTaxLiabilitiesNet": "Deferred income tax liabilities, net",
    "DeferredIncomeTaxLiabilities": "Deferred income tax liabilities",
    "DeferredTaxLiabilities": "Deferred tax liabilities",
    "DeferredIncomeTaxesAndOtherTaxLiabilitiesNoncurrent": (
        "Deferred income taxes and other tax liabilities"
    ),
    "MarketRiskBenefitLiabilityAmount": "Market risk benefits (liability)",
    "DerivativeLiabilities": "Derivative liabilities",
    "SeparateAccountsLiability": "Separate accounts liability",
    "LiabilityForClaimsAndClaimsAdjustmentExpense": (
        "Liability for claims and claims adjustment expense"
    ),
    "SupplementaryInsuranceInformationOtherPolicyClaimsAndBenefitsPayable": (
        "Other policy claims and benefits payable (insurance information)"
    ),
    "LiabilityForFuturePolicyBenefits": "Liability for future policy benefits",
    "OtherPolicyholderFunds": "Other policyholder funds",
    "AssetRetirementObligationsNoncurrent": "Asset retirement obligations (non-current)",
    "AssetRetirementObligation": "Asset retirement obligations",
    "DeferredCreditsAndOtherLiabilities": "Deferred credits and other liabilities",
    "PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent": (
        "Pension and other postretirement benefit obligations"
    ),
    "OtherLiabilitiesNoncurrent": "Other non-current liabilities",
    "OtherLiabilities": "Other liabilities",
    # --- Equity ----------------------------------------------------------
    "PreferredStockValue": "Preferred stock",
    "PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount": (
        "Preferred stock incl. additional paid-in capital"
    ),
    "CommonStockValue": "Common stock",
    "CommonStocksIncludingAdditionalPaidInCapital": (
        "Common stock incl. additional paid-in capital"
    ),
    "AdditionalPaidInCapital": "Additional paid-in capital",
    "AdditionalPaidInCapitalCommonStock": "Additional paid-in capital (common stock)",
    "PaidInCapital": "Paid-in capital",
    "RetainedEarningsAccumulatedDeficit": "Retained earnings (accumulated deficit)",
    "RetainedEarnings": "Retained earnings",
    "TreasuryStockValue": "Treasury stock",
    "TreasuryStockCommonValue": "Treasury stock (common stock)",
    "AccumulatedOtherComprehensiveIncomeLossNetOfTax": (
        "Accumulated other comprehensive income (loss)"
    ),
    "MinorityInterest": "Minority interest",
    "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests": (
        "Temporary (mezzanine) equity"
    ),
    "TemporaryEquityCarryingAmount": "Temporary (mezzanine) equity",
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
    "AccountsNotesAndLoansReceivableNetCurrent": "Accounts Notes And Loans Receivable Net Current",
    "AccountsReceivableBilledForLongTermContractsOrPrograms": "Accounts Receivable Billed For Long Term Contracts Or Programs",
    "AccountsReceivableGross": "Accounts Receivable Gross",
    "AccountsReceivableGrossCurrent": "Accounts Receivable Gross Current",
    "AccretionAmortizationOfDiscountsAndPremiumsInvestments": "Accretion Amortization Of Discounts And Premiums Investments",
    "AccrualForEnvironmentalLossContingencies": "Accrual For Environmental Loss Contingencies",
    "AccrualForEnvironmentalLossContingenciesChargesToExpenseForNewLosses": "Accrual For Environmental Loss Contingencies Charges To Expense For New Losses",
    "AccrualForEnvironmentalLossContingenciesGross": "Accrual For Environmental Loss Contingencies Gross",
    "AccrualForEnvironmentalLossContingenciesIncreaseDecreaseForRevisionInEstimates": "Accrual For Environmental Loss Contingencies Increase Decrease For Revision In Estimates",
    "AccrualForEnvironmentalLossContingenciesPayments1": "Accrual For Environmental Loss Contingencies Payments1",
    "AccrualForTaxesOtherThanIncomeTaxesCurrent": "Accrual For Taxes Other Than Income Taxes Current",
    "AccruedAdvertisingCurrent": "Accrued Advertising Current",
    "AccruedBonusesCurrent": "Accrued Bonuses Current",
    "AccruedEmployeeBenefitsCurrent": "Accrued Employee Benefits Current",
    "AccruedEmployeeBenefitsCurrentAndNoncurrent": "Accrued Employee Benefits Current And Noncurrent",
    "AccruedEnvironmentalLossContingenciesCurrent": "Accrued Environmental Loss Contingencies Current",
    "AccruedEnvironmentalLossContingenciesNoncurrent": "Accrued Environmental Loss Contingencies Noncurrent",
    "AccruedIncomeTaxes": "Accrued Income Taxes",
    "AccruedIncomeTaxesNoncurrent": "Accrued Income Taxes Noncurrent",
    "AccruedInsuranceCurrent": "Accrued Insurance Current",
    "AccruedInvestmentIncomeReceivable": "Accrued Investment Income Receivable",
    "AccruedMarketingCostsCurrent": "Accrued Marketing Costs Current",
    "AccruedProfessionalFeesCurrent": "Accrued Professional Fees Current",
    "AccruedRentCurrent": "Accrued Rent Current",
    "AccruedRoyaltiesCurrent": "Accrued Royalties Current",
    "AccruedSalesCommissionCurrentAndNoncurrent": "Accrued Sales Commission Current And Noncurrent",
    "AccumulatedDeferredInvestmentTaxCredit": "Accumulated Deferred Investment Tax Credit",
    "AccumulatedOtherComprehensiveIncomeLossAvailableForSaleSecuritiesAdjustmentNetOfTax": "Accumulated Other Comprehensive Income Loss Available For Sale Securities Adjustment Net Of Tax",
    "AccumulatedOtherComprehensiveIncomeLossDefinedBenefitPensionAndOtherPostretirementPlansNetOfTax": "Accumulated Other Comprehensive Income Loss Defined Benefit Pension And Other Postretirement Plans Net Of Tax",
    "AccumulatedOtherComprehensiveIncomeLossForeignCurrencyTranslationAdjustmentNetOfTax": "Accumulated Other Comprehensive Income Loss Foreign Currency Translation Adjustment Net Of Tax",
    "AdditionalCollateralAggregateFairValue": "Additional Collateral Aggregate Fair Value",
    "AdditionsToContractHoldersFunds": "Additions To Contract Holders Funds",
    "AdjustmentForAmortization": "Adjustment For Amortization",
    "AdjustmentsRelatedToTaxWithholdingForShareBasedCompensation": "Adjustments Related To Tax Withholding For Share Based Compensation",
    "AdjustmentsToAdditionalPaidInCapitalSharebasedCompensationRequisiteServicePeriodRecognitionValue": "Adjustments To Additional Paid In Capital Sharebased Compensation Requisite Service Period Recognition Value",
    "AdjustmentsToReconcileNetIncomeLossToCashProvidedByUsedInOperatingActivities": "Adjustments To Reconcile Net Income Loss To Cash Provided By Used In Operating Activities",
    "AdvanceRent": "Advance Rent",
    "AdvertisingExpense": "Advertising Expense",
    "AffordableHousingTaxCreditsAndOtherTaxBenefitsAmount": "Affordable Housing Tax Credits And Other Tax Benefits Amount",
    "AllocatedShareBasedCompensationExpense": "Allocated Share Based Compensation Expense",
    "AllocatedShareBasedCompensationExpenseNetOfTax": "Allocated Share Based Compensation Expense Net Of Tax",
    "AllowanceForDoubtfulAccountsReceivable": "Allowance For Doubtful Accounts Receivable",
    "AllowanceForDoubtfulAccountsReceivableCurrent": "Allowance For Doubtful Accounts Receivable Current",
    "AllowanceForDoubtfulAccountsReceivableWriteOffs": "Allowance For Doubtful Accounts Receivable Write Offs",
    "AllowanceForNotesAndLoansReceivableCurrent": "Allowance For Notes And Loans Receivable Current",
    "AmortizationOfAboveAndBelowMarketLeases": "Amortization Of Above And Below Market Leases",
    "AmortizationOfDebtDiscountPremium": "Amortization Of Debt Discount Premium",
    "AmortizationOfFinancingCosts": "Amortization Of Financing Costs",
    "AmortizationOfFinancingCostsAndDiscounts": "Amortization Of Financing Costs And Discounts",
    "AmortizationOfIntangibleAssets": "Amortization Of Intangible Assets",
    "AntidilutiveSecuritiesExcludedFromComputationOfEarningsPerShareAmount": "Antidilutive Securities Excluded From Computation Of Earnings Per Share Amount",
    "AvailableForSaleDebtSecuritiesAccumulatedGrossUnrealizedGainBeforeTax": "Available For Sale Debt Securities Accumulated Gross Unrealized Gain Before Tax",
    "AvailableForSaleDebtSecuritiesAccumulatedGrossUnrealizedLossBeforeTax": "Available For Sale Debt Securities Accumulated Gross Unrealized Loss Before Tax",
    "AvailableForSaleDebtSecuritiesAmortizedCostBasis": "Available For Sale Debt Securities Amortized Cost Basis",
    "AvailableForSaleSecuritiesDebtMaturitiesAfterFiveThroughTenYearsAmortizedCost": "Available For Sale Securities Debt Maturities After Five Through Ten Years Amortized Cost",
    "BelowMarketLeaseNet": "Below Market Lease Net",
    "BuildingsAndImprovementsGross": "Buildings And Improvements Gross",
    "CapitalExpendituresIncurredButNotYetPaid": "Capital Expenditures Incurred But Not Yet Paid",
    "Cash": "Cash",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect": "Cash Cash Equivalents Restricted Cash And Restricted Cash Equivalents Period Increase Decrease Including Exchange Rate Effect",
    "CashProvidedByUsedInFinancingActivitiesDiscontinuedOperations": "Cash Provided By Used In Financing Activities Discontinued Operations",
    "CashProvidedByUsedInInvestingActivitiesDiscontinuedOperations": "Cash Provided By Used In Investing Activities Discontinued Operations",
    "CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations": "Cash Provided By Used In Operating Activities Discontinued Operations",
    "CoSelectedMeasureAmt": "Co Selected Measure Amt",
    "CommonStockDividendsPerShareCashPaid": "Common Stock Dividends Per Share Cash Paid",
    "CommonStockDividendsPerShareDeclared": "Common Stock Dividends Per Share Declared",
    "ComprehensiveIncomeNetOfTaxAttributableToNoncontrollingInterest": "Comprehensive Income Net Of Tax Attributable To Noncontrolling Interest",
    "ComprehensiveIncomeNetOfTaxIncludingPortionAttributableToNoncontrollingInterest": "Comprehensive Income Net Of Tax Including Portion Attributable To Noncontrolling Interest",
    "ContractualObligation": "Contractual Obligation",
    "CostOfRevenue": "Cost Of Revenue",
    "CostsAndExpenses": "Costs And Expenses",
    "CurrentIncomeTaxExpenseBenefit": "Current Income Tax Expense Benefit",
    "DebtInstrumentInterestRateEffectivePercentage": "Debt Instrument Interest Rate Effective Percentage",
    "DeferredRevenue": "Deferred Revenue",
    "Depreciation": "Depreciation",
    "DepreciationAndAmortization": "Depreciation And Amortization",
    "DepreciationDepletionAndAmortization": "Depreciation Depletion And Amortization",
    "DividendsCommonStockCash": "Dividends Common Stock Cash",
    "DividendsPreferredStockCash": "Dividends Preferred Stock Cash",
    "IncomeTaxesPaidNet": "Income Taxes Paid Net",
    "IncreaseDecreaseInAccountsAndNotesReceivable": "Increase Decrease In Accounts And Notes Receivable",
    "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities": "Increase Decrease In Accounts Payable And Accrued Liabilities",
    "IncreaseDecreaseInAccountsPayableTrade": "Increase Decrease In Accounts Payable Trade",
    "IncreaseDecreaseInAccountsReceivableAndOtherOperatingAssets": "Increase Decrease In Accounts Receivable And Other Operating Assets",
    "IncreaseDecreaseInAccruedIncomeTaxesPayable": "Increase Decrease In Accrued Income Taxes Payable",
    "IncreaseDecreaseInAccruedLiabilities": "Increase Decrease In Accrued Liabilities",
    "IncreaseDecreaseInAccruedLiabilitiesAndOtherOperatingLiabilities": "Increase Decrease In Accrued Liabilities And Other Operating Liabilities",
    "IncreaseDecreaseInDeferredLeasingFees": "Increase Decrease In Deferred Leasing Fees",
    "IncreaseDecreaseInDeferredPolicyAcquisitionCosts": "Increase Decrease In Deferred Policy Acquisition Costs",
    "IncreaseDecreaseInDeferredRevenue": "Increase Decrease In Deferred Revenue",
    "IncreaseDecreaseInEquitySecuritiesFvNi": "Increase Decrease In Equity Securities FV-NI",
    "IncreaseDecreaseInInsuranceLiabilities": "Increase Decrease In Insurance Liabilities",
    "IncreaseDecreaseInLeasingReceivables": "Increase Decrease In Leasing Receivables",
    "IncreaseDecreaseInOperatingLiabilities": "Increase Decrease In Operating Liabilities",
    "IncreaseDecreaseInOtherNoncurrentLiabilities": "Increase Decrease In Other Noncurrent Liabilities",
    "IncreaseDecreaseInOtherOperatingCapitalNet": "Increase Decrease In Other Operating Capital Net",
    "IncreaseDecreaseInPensionAndPostretirementObligations": "Increase Decrease In Pension And Postretirement Obligations",
    "IncreaseDecreaseInPremiumsReceivable": "Increase Decrease In Premiums Receivable",
    "IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets": "Increase Decrease In Prepaid Deferred Expense And Other Assets",
    "IncreaseDecreaseInTradingSecurities": "Increase Decrease In Trading Securities",
    "NetIncomeLossAvailableToCommonStockholdersBasic": "Net Income Loss Available To Common Stockholders Basic",
    "NonPeoNeoAvgCompActuallyPaidAmt": "Non PEO NEO Avg Comp Actually Paid Amt",
    "NonPeoNeoAvgTotalCompAmt": "Non PEO NEO Avg Total Comp Amt",
    "OperatingExpenses": "Operating Expenses",
    "PaymentsForHedgeInvestingActivities": "Payments For Hedge Investing Activities",
    "PaymentsForLeasingCostsCommissionsAndTenantImprovements": "Payments For Leasing Costs Commissions And Tenant Improvements",
    "PaymentsOfStockIssuanceCosts": "Payments Of Stock Issuance Costs",
    "ResearchAndDevelopmentExpense": "Research And Development Expense",
    "ShareBasedCompensation": "Share Based Compensation",
    "StockRepurchasedDuringPeriodValue": "Stock Repurchased During Period Value",
}


def label(concept: str) -> str:
    """Human label for a concept in English (falls back to humanization)."""
    return FIELD_LABELS.get(concept) or humanize_concept(concept)
