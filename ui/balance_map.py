"""XBRL balance-sheet concepts -> the five masses of the classic T layout.

The T view is a curated presentation of the raw XBRL facts: this map decides
which concept renders in which mass and in what order. It is the UI-side
mirror of ``backend.repositories.fdb_concept_mapping.BALANCE_SHEET_CONCEPTS``
(read-only): keys there that are share counts or pure ratios live here as
*memoranda* (never in the monetary masses).

Each mass entry is a list of *slots*; a slot is a list of alias concepts that
describe the same line (``["CashAndCashEquivalentsAtCarryingValue",
"CashAndCashEquivalents"]``). When a filing reports several aliases for one
slot only the first present concept is shown — never double counted.

Two slots break the "first alias wins" order because the aliases are not
siblings but an aggregate and its parts:

* a **zero** never wins over a non-zero alias of the same slot (a filer that
  tags a net deferred-tax concept as ``0`` still reports the balance-sheet
  amount under the gross tag);
* a slot listed in :data:`AGGREGATE_SLOTS` renders the **largest** amount of
  its aliases, so the aggregate wins over the components that add up to it.
"""

from __future__ import annotations

#: Mass key -> ordered alias-slots of the concept lines it contains.
#:
#: Slots hold *aliases of the same face line*, not every concept that adds
#: up to it: a filer that reports a total (``Investments``) and its parts
#: (``AvailableForSaleSecuritiesDebtSecurities``) keeps them in one slot so
#: only the first present concept is shown. Sector-specific face lines
#: (banks, insurers, REITs, utilities, oil & gas) get their own slot so they
#: are rendered instead of falling into "unclassified" leftovers.
BALANCE_MAP: dict[str, list[list[str]]] = {
    "assets_current": [
        # Cash. Banks tag "cash and due from banks" next to "deposits with
        # banks" and their restricted-cash tag is the *sum* of both, so the
        # bank-specific tag comes first and the combined tag last.
        [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashAndCashEquivalents",
            "CashAndDueFromBanks",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ],
        ["ShortTermInvestments", "MarketableSecuritiesCurrent"],
        [
            "ReceivablesNetCurrent",
            "AccountsReceivableNetCurrent",
            "AccountsReceivableNet",
            "AccountsAndOtherReceivablesNetCurrent",
            "PremiumsAndOtherReceivablesNet",
            "PremiumsReceivableAtCarryingValue",
        ],
        ["NontradeReceivablesCurrent"],
        # Inventory: filers tag the total and the components (materials and
        # supplies); only the first present concept is rendered.
        [
            "InventoryNet",
            "EnergyRelatedInventory",
            "InventoryPartsAndComponentsNetOfReserves",
        ],
        ["PrepaidExpenseAndOtherAssetsCurrent", "OtherAssetsCurrent"],
        # Banks: reverse repos (a face line of their balance sheet).
        [
            "FederalFundsSoldAndSecuritiesPurchasedUnderAgreementsToResell",
            "SecuritiesPurchasedUnderAgreementsToResell",
        ],
        # Banks: deposits with banks (their own face line).
        ["InterestBearingDepositsInBanks"],
    ],
    "assets_noncurrent": [
        # Property and equipment: net, gross and accumulated depreciation are
        # three distinct lines. The oil & gas tags come before the finance
        # lease ones, which are note-level detail of the same filer.
        [
            "PropertyPlantAndEquipmentNet",
            "CapitalizedCostsOilAndGasProducingActivitiesNet",
            "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
            "PublicUtilitiesPropertyPlantAndEquipmentNet",
            "RealEstateInvestmentPropertyNet",
        ],
        [
            "PropertyPlantAndEquipmentGross",
            "CapitalizedCostsOilAndGasProducingActivitiesGross",
            "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetBeforeAccumulatedDepreciationAndAmortization",
            "PublicUtilitiesPropertyPlantAndEquipmentPlantInService",
            "RealEstateGrossAtCarryingValue",
            "OilAndGasPropertySuccessfulEffortMethodGross",
        ],
        [
            "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
            "CapitalizedCostsAccumulatedDepreciationDepletionAmortizationAndValuationAllowanceForRelatingToOilAndGasProducingActivities",
            "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAccumulatedDepreciationAndAmortization",
            "PublicUtilitiesPropertyPlantAndEquipmentAccumulatedDepreciation",
            "RealEstateAccumulatedDepreciation",
            "RealEstateInvestmentPropertyAccumulatedDepreciation",
        ],
        ["Goodwill"],
        [
            "IntangibleAssetsNetExcludingGoodwill",
            "FiniteLivedIntangibleAssetsNet",
            "IndefiniteLivedIntangibleAssetsExcludingGoodwill",
            "OtherIntangibleAssetsNet",
        ],
        # Investments: a filer that reports a total ("Investments") and its
        # parts keeps them in one slot, so only the first present concept is
        # rendered (the total first, then the disaggregated tags).
        [
            "Investments",
            "MarketableSecurities",
            "EquitySecuritiesFvNi",
            "EquitySecuritiesFvNiCurrentAndNoncurrent",
            "LongTermInvestmentsAndReceivablesNet",
            "AvailableForSaleSecuritiesDebtSecurities",
            "DebtSecuritiesAvailableForSaleExcludingAccruedInterest",
            "OtherInvestments",
            "EquityMethodInvestments",
            "InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures",
            "MarketableSecuritiesNoncurrent",
            "LongTermInvestments",
        ],
        # Loans and notes receivable (banks, insurers, REITs).
        [
            "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss",
            "NotesReceivableNet",
        ],
        # Banks: held-to-maturity securities (their own face line).
        [
            "DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss",
            "DebtSecuritiesHeldToMaturityExcludingAccruedInterestBeforeAllowanceForCreditLoss",
        ],
        # Banks and asset managers: securities borrowed (a receivable).
        ["SecuritiesBorrowed"],
        # Insurers: separate account assets and market risk benefits.
        ["SeparateAccountAssets"],
        ["MarketRiskBenefitAssetAmount"],
        # Deferred tax assets: the net tag first, the gross tag only fills in
        # for filers that do not report the net one.
        [
            "DeferredIncomeTaxAssetsNet",
            "DeferredTaxAssetsNet",
            "DeferredTaxAssetsNoncurrent",
        ],
        [
            "OtherAssetsNoncurrent",
            "OtherAssets",
            "OtherAssetsMiscellaneous",
            "OtherAssetsMiscellaneousNoncurrent",
            "RegulatedEntityOtherAssetsNoncurrent",
            "DeferredIncomeTaxesAndOtherAssetsNoncurrent",
        ],
        # Sector-specific non-current assets.
        ["AssetsHeldByInsuranceRegulators"],
        ["RegulatoryAssetsNoncurrent"],
        ["DeferredPolicyAcquisitionCosts"],
        [
            "ReinsuranceRecoverables",
            "ReinsuranceRecoverablesGross",
            "ReinsuranceRecoverableForUnpaidClaimsAndClaimsAdjustments",
            "ReinsuranceRecoverablesOnPaidAndUnpaidLosses",
        ],
        ["OperatingLeaseRightOfUseAsset"],
        [
            "DeferredRentReceivablesNet",
            "DeferredRentReceivablesNetNoncurrent",
        ],
    ],
    "liab_current": [
        # Current debt: the aliases mix a filer's aggregate ("Debt current")
        # with its components (commercial paper, current maturities), so the
        # largest amount wins (see AGGREGATE_SLOTS).
        [
            "ShortTermBorrowings",
            "DebtCurrent",
            "CommercialPaper",
            "LongTermDebtCurrent",
            "LongTermDebtAndCapitalLeaseObligationsCurrent",
            "OtherShortTermBorrowings",
        ],
        [
            "AccountsPayableCurrent",
            "AccountsPayableAndAccruedLiabilitiesCurrent",
            "AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent",
            "AccountsPayableAndOtherAccruedLiabilities",
            "AccountsPayableCurrentAndNoncurrent",
            "AccountsPayableTradeCurrent",
            "AccountsPayableOtherCurrent",
        ],
        # Accrued and other current liabilities: filers report the aggregate
        # ("Other liabilities, current") and its parts (accrued compensation,
        # warranty accruals...), so a single line is rendered.
        [
            "AccruedLiabilitiesCurrent",
            "AccruedLiabilitiesAndOtherLiabilities",
            "OtherAccruedLiabilitiesCurrent",
            "OtherLiabilitiesCurrent",
            "EmployeeRelatedLiabilitiesCurrent",
            "StandardProductWarrantyAccrual",
        ],
        # Income taxes payable: a face line of its own for most filers.
        ["AccruedIncomeTaxesCurrent", "TaxesPayableCurrent"],
        # Interest payable: a face line of its own for most filers.
        ["InterestPayableCurrent"],
        [
            "ContractWithCustomerLiabilityCurrent",
            "ContractWithCustomerLiability",
            "DeferredRevenueCurrent",
        ],
        # Sector-specific current liabilities.
        ["UnearnedPremiums", "SupplementaryInsuranceInformationUnearnedPremiums"],
        # Deposits (banks) and policyholder funds (insurers): the totals and
        # their breakdowns share one slot so only one of them is rendered.
        [
            "PolicyholderContractDeposits",
            "PolicyholderFunds",
            "Deposits",
            "InterestBearingDepositLiabilities",
            "NoninterestBearingDepositLiabilities",
            "DepositsDomestic",
            "InterestBearingDepositLiabilitiesDomestic",
            "NoninterestBearingDepositLiabilitiesDomestic",
            "DemandDepositAccounts",
            "DepositsSavingsDeposits",
            "DepositsMoneyMarketDeposits",
            "TimeDeposits",
        ],
        # Federal funds purchased and securities sold under repurchase
        # agreements: the combined tag comes first (it is the face line).
        [
            "FederalFundsPurchasedAndSecuritiesSoldUnderAgreementsToRepurchase",
            "SecuritiesSoldUnderAgreementsToRepurchase",
        ],
        ["TradingLiabilities"],
        [
            "DividendsPayableCurrent",
            "DividendsPayableCurrentAndNoncurrent",
            "DividendsPayableNoncurrent",
        ],
    ],
    "liab_noncurrent": [
        [
            "LongTermDebtNoncurrent",
            "DebtNoncurrent",
            "LongTermDebt",
            "LongTermDebtAndCapitalLeaseObligations",
            "SeniorLongTermNotes",
            "LongTermNotesPayable",
            "UnsecuredDebt",
            "DebtAndCapitalLeaseObligations",
            "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
        ],
        [
            "LongTermLiabilities",
            "LiabilitiesOtherThanLongtermDebtNoncurrent",
            "RegulatoryLiabilityNoncurrent",
            "RegulatoryLiabilities",
        ],
        ["OperatingLeaseLiabilityNoncurrent", "OperatingLeaseLiability"],
        ["FinanceLeaseLiabilityNoncurrent", "FinanceLeaseLiability"],
        # Deferred income taxes: the net tag first, the gross tag only fills
        # in for filers that do not report the net one.
        [
            "DeferredIncomeTaxLiabilitiesNet",
            "DeferredTaxLiabilitiesNet",
            "DeferredTaxLiabilitiesNoncurrent",
            "DeferredIncomeTaxLiabilities",
            "DeferredTaxLiabilities",
            "DeferredIncomeTaxesAndOtherTaxLiabilitiesNoncurrent",
        ],
        [
            "OtherLiabilitiesNoncurrent",
            "OtherLiabilities",
            "AssetRetirementObligationsNoncurrent",
            "AssetRetirementObligation",
            "DeferredCreditsAndOtherLiabilities",
        ],
        # Pension and other postretirement obligations (their own face line).
        ["PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent"],
        # Sector-specific non-current liabilities.
        [
            "LiabilityForClaimsAndClaimsAdjustmentExpense",
            "SupplementaryInsuranceInformationOtherPolicyClaimsAndBenefitsPayable",
        ],
        ["LiabilityForFuturePolicyBenefits"],
        ["OtherPolicyholderFunds"],
        ["DerivativeLiabilities"],
        ["MarketRiskBenefitLiabilityAmount"],
        ["SeparateAccountsLiability"],
    ],
    "equity": [
        [
            "PreferredStockValue",
            "PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount",
        ],
        # Combined tag (e.g. Apple files common stock + APIC as one line);
        # filers using the separate tags still resolve the usual two lines.
        ["CommonStockValue", "CommonStocksIncludingAdditionalPaidInCapital"],
        [
            "AdditionalPaidInCapital",
            "PaidInCapital",
            "AdditionalPaidInCapitalCommonStock",
        ],
        ["RetainedEarningsAccumulatedDeficit", "RetainedEarnings"],
        ["TreasuryStockValue", "TreasuryStockCommonValue"],
        ["AccumulatedOtherComprehensiveIncomeLossNetOfTax"],
        ["MinorityInterest"],
        # Temporary (mezzanine) equity: reported between liabilities and
        # equity, shown as the last line of the equity column.
        [
            "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests",
            "TemporaryEquityCarryingAmount",
        ],
    ],
}

#: Slots whose aliases are an aggregate and its components rather than plain
#: siblings: the **largest** amount wins, so the aggregate is rendered and
#: the components that add up to it stay hidden. Mass key -> slot indexes.
AGGREGATE_SLOTS: dict[str, set[int]] = {
    "liab_current": {0},
}

#: Mass key -> concepts a filer may report as that mass's own subtotal.
#: When several are present the first wins; when none is, the UI computes
#: the subtotal from the lines and labels it as computed.
MASS_SUBTOTAL_CONCEPTS: dict[str, list[str]] = {
    "assets_current": ["AssetsCurrent"],
    "assets_noncurrent": ["AssetsNoncurrent"],
    "liab_current": ["LiabilitiesCurrent"],
    "liab_noncurrent": ["LiabilitiesNoncurrent"],
    "equity": [
        "StockholdersEquity",
        "ShareholdersEquity",
        "TotalEquityGrossMinorityInterest",
    ],
}

#: Statement totals, in resolution priority order. ``total_assets`` falls
#: back to the accounting-identity tag when ``Assets`` is not filed.
TOTAL_CONCEPTS: dict[str, list[str]] = {
    "total_assets": ["Assets", "AssetsTotal", "LiabilitiesAndStockholdersEquity"],
    "total_liabilities": ["Liabilities", "LiabilitiesTotal"],
}

#: Balance-bucket concepts that are NOT monetary lines (share counts, public
#: float): shown as a memoranda footnote, never inside the masses.
MEMORANDUM_CONCEPTS: set[str] = {
    "CommonStockSharesOutstanding",
    "CommonStockSharesIssued",
    "CommonStockSharesAuthorized",
    "EntityCommonStockSharesOutstanding",
    "EntityPublicFloat",
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfSharesOutstanding",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingDiluted",
    "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
}

#: Contra lines reported as positive numbers that must render (and sum) as
#: negatives — e.g. accumulated depreciation against gross PP&E. Every
#: accumulated-depreciation alias in the map belongs here, otherwise the
#: contra line would add to the subtotal instead of reducing it.
CONTRA_CONCEPTS: set[str] = {
    "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
    "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAccumulatedDepreciationAndAmortization",
    "PublicUtilitiesPropertyPlantAndEquipmentAccumulatedDepreciation",
    "RealEstateAccumulatedDepreciation",
    "RealEstateInvestmentPropertyAccumulatedDepreciation",
}

#: Display order of the masses (left column, then right column).
MASS_ORDER: list[str] = [
    "assets_current",
    "assets_noncurrent",
    "liab_current",
    "liab_noncurrent",
    "equity",
]

#: Which column of the T each mass belongs to.
MASS_COLUMN: dict[str, str] = {
    "assets_current": "assets",
    "assets_noncurrent": "assets",
    "liab_current": "liabilities",
    "liab_noncurrent": "liabilities",
    "equity": "liabilities",
}

#: Mass key -> English header label.
MASS_LABELS: dict[str, str] = {
    "assets_current": "Current assets",
    "assets_noncurrent": "Non-current assets",
    "liab_current": "Current liabilities",
    "liab_noncurrent": "Non-current liabilities",
    "equity": "Shareholders' equity",
}


def mass_labels(key: str) -> str:
    """Mass header label in English."""
    return MASS_LABELS.get(key, "")


def concept_mass(concept: str) -> str | None:
    """Mass a concept belongs to, ``None`` when the concept is unmapped."""
    for mass, slots in BALANCE_MAP.items():
        for slot in slots:
            if concept in slot:
                return mass
    return None


def mass_slot_index(concept: str) -> tuple[str, int] | None:
    """``(mass, slot)`` position of a concept, or ``None`` when unmapped."""
    for mass, slots in BALANCE_MAP.items():
        for index, slot in enumerate(slots):
            if concept in slot:
                return mass, index
    return None


def subtotal_concept(mass: str) -> str | None:
    """The reported subtotal concept to paint for ``mass``, if any."""
    concepts = MASS_SUBTOTAL_CONCEPTS.get(mass, [])
    return concepts[0] if concepts else None


def is_memorandum(concept: str) -> bool:
    """True for non-monetary balance-bucket concepts (share counts etc.)."""
    return concept in MEMORANDUM_CONCEPTS


def mapped_concepts() -> set[str]:
    """Every concept the map can place in a mass (aliases flattened)."""
    return {
        concept for slots in BALANCE_MAP.values() for slot in slots for concept in slot
    }
