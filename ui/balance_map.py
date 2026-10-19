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
"""

from __future__ import annotations

#: Mass key -> ordered alias-slots of the concept lines it contains.
BALANCE_MAP: dict[str, list[list[str]]] = {
    "assets_current": [
        [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashAndCashEquivalents",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ],
        ["ShortTermInvestments", "MarketableSecuritiesCurrent"],
        ["AccountsReceivableNetCurrent", "AccountsReceivableNet"],
        ["NontradeReceivablesCurrent"],
        ["InventoryNet"],
        ["PrepaidExpenseAndOtherAssetsCurrent", "OtherAssetsCurrent"],
    ],
    "assets_noncurrent": [
        ["PropertyPlantAndEquipmentNet"],
        ["PropertyPlantAndEquipmentGross"],
        ["AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment"],
        ["Goodwill"],
        ["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"],
        ["LongTermInvestments", "MarketableSecuritiesNoncurrent"],
        ["DeferredTaxAssetsNoncurrent"],
        ["OtherAssetsNoncurrent"],
    ],
    "liab_current": [
        ["ShortTermBorrowings", "CommercialPaper"],
        ["DebtCurrent", "LongTermDebtCurrent"],
        [
            "AccountsPayableCurrent",
            "AccountsPayableAndAccruedLiabilitiesCurrent",
            "AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent",
            "AccountsPayableAndOtherAccruedLiabilities",
        ],
        ["AccruedLiabilitiesCurrent"],
        ["ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"],
        ["OtherLiabilitiesCurrent"],
    ],
    "liab_noncurrent": [
        ["LongTermDebtNoncurrent", "DebtNoncurrent", "LongTermDebt"],
        ["LongTermLiabilities"],
        ["OperatingLeaseLiabilityNoncurrent"],
        ["FinanceLeaseLiabilityNoncurrent"],
        ["DeferredTaxLiabilitiesNoncurrent", "DeferredTaxLiabilitiesNet"],
        ["OtherLiabilitiesNoncurrent"],
    ],
    "equity": [
        ["PreferredStockValue"],
        # Combined tag (e.g. Apple files common stock + APIC as one line);
        # filers using the separate tags still resolve the usual two lines.
        ["CommonStockValue", "CommonStocksIncludingAdditionalPaidInCapital"],
        ["AdditionalPaidInCapital", "PaidInCapital"],
        ["RetainedEarningsAccumulatedDeficit", "RetainedEarnings"],
        ["TreasuryStockValue"],
        ["AccumulatedOtherComprehensiveIncomeLossNetOfTax"],
        ["MinorityInterest"],
    ],
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
#: negatives — e.g. accumulated depreciation against gross PP&E.
CONTRA_CONCEPTS: set[str] = {
    "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
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
    return {concept for slots in BALANCE_MAP.values() for slot in slots for concept in slot}
