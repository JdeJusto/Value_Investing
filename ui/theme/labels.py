"""Human labels for financial statement lines (ES primary, EN fallback).

Central map ``FIELD_LABELS``: XBRL concept -> ``{"es": ..., "en": ...}``.
The Balance T-view and the statement tables all resolve labels here so a
concept never shows its raw technical name (``cash_and_equivalents``) on
screen. Unknown concepts fall back to the English humanization from the
read-only backend view service (``humanize_concept``).
"""

from __future__ import annotations

from backend.services.financials_view_service import humanize_concept

#: XBRL concept -> {language: label}. "es" is the default display language.
FIELD_LABELS: dict[str, dict[str, str]] = {
    # --- Totals ---------------------------------------------------------
    "Assets": {"es": "Total activo", "en": "Total assets"},
    "AssetsTotal": {"es": "Total activo", "en": "Total assets"},
    "LiabilitiesAndStockholdersEquity": {
        "es": "Total pasivo + patrimonio neto",
        "en": "Total liabilities and stockholders' equity",
    },
    "Liabilities": {"es": "Total pasivo", "en": "Total liabilities"},
    "LiabilitiesTotal": {"es": "Total pasivo", "en": "Total liabilities"},
    # --- Subtotals (reported masses) ------------------------------------
    "AssetsCurrent": {"es": "Total activo corriente", "en": "Total current assets"},
    "AssetsNoncurrent": {
        "es": "Total activo no corriente",
        "en": "Total non-current assets",
    },
    "LiabilitiesCurrent": {
        "es": "Total pasivo corriente",
        "en": "Total current liabilities",
    },
    "LiabilitiesNoncurrent": {
        "es": "Total pasivo no corriente",
        "en": "Total non-current liabilities",
    },
    "StockholdersEquity": {
        "es": "Total patrimonio neto",
        "en": "Total stockholders' equity",
    },
    "ShareholdersEquity": {
        "es": "Total patrimonio neto",
        "en": "Total shareholders' equity",
    },
    "TotalEquityGrossMinorityInterest": {
        "es": "Total patrimonio neto (con control minoritario)",
        "en": "Total equity incl. minority interest",
    },
    # --- Current assets -------------------------------------------------
    "CashAndCashEquivalentsAtCarryingValue": {
        "es": "Efectivo y equivalentes",
        "en": "Cash and cash equivalents",
    },
    "CashAndCashEquivalents": {
        "es": "Efectivo y equivalentes",
        "en": "Cash and cash equivalents",
    },
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": {
        "es": "Efectivo, equivalentes y efectivo restringido",
        "en": "Cash, cash equivalents and restricted cash",
    },
    "ShortTermInvestments": {"es": "Inversiones a corto plazo", "en": "Short-term investments"},
    "MarketableSecuritiesCurrent": {
        "es": "Valores negociables a corto plazo",
        "en": "Marketable securities (current)",
    },
    "AccountsReceivableNetCurrent": {
        "es": "Deudores comerciales",
        "en": "Accounts receivable, net (current)",
    },
    "AccountsReceivableNet": {"es": "Deudores comerciales", "en": "Accounts receivable, net"},
    "NontradeReceivablesCurrent": {
        "es": "Deudores no comerciales",
        "en": "Non-trade receivables (current)",
    },
    "InventoryNet": {"es": "Inventarios", "en": "Inventory, net"},
    "PrepaidExpenseAndOtherAssetsCurrent": {
        "es": "Gastos pagados por anticipado y otros activos",
        "en": "Prepaid expenses and other current assets",
    },
    "OtherAssetsCurrent": {"es": "Otros activos corrientes", "en": "Other current assets"},
    # --- Non-current assets ---------------------------------------------
    "PropertyPlantAndEquipmentNet": {
        "es": "Inmovilizado material (neto)",
        "en": "Property, plant and equipment, net",
    },
    "PropertyPlantAndEquipmentGross": {
        "es": "Inmovilizado material (bruto)",
        "en": "Property, plant and equipment, gross",
    },
    "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment": {
        "es": "Depreciación y amortización acumuladas",
        "en": "Accumulated depreciation, depletion and amortization",
    },
    "Goodwill": {"es": "Goodwill", "en": "Goodwill"},
    "IntangibleAssetsNetExcludingGoodwill": {
        "es": "Intangibles (neto, sin goodwill)",
        "en": "Intangible assets, net (excl. goodwill)",
    },
    "FiniteLivedIntangibleAssetsNet": {
        "es": "Intangibles de vida finita (neto)",
        "en": "Finite-lived intangible assets, net",
    },
    "LongTermInvestments": {"es": "Inversiones a largo plazo", "en": "Long-term investments"},
    "MarketableSecuritiesNoncurrent": {
        "es": "Valores negociables a largo plazo",
        "en": "Marketable securities (non-current)",
    },
    "DeferredTaxAssetsNoncurrent": {
        "es": "Activos fiscales diferidos",
        "en": "Deferred tax assets (non-current)",
    },
    "OtherAssetsNoncurrent": {"es": "Otros activos no corrientes", "en": "Other non-current assets"},
    # --- Current liabilities --------------------------------------------
    "ShortTermBorrowings": {"es": "Préstamos a corto plazo", "en": "Short-term borrowings"},
    "CommercialPaper": {"es": "Papel comercial", "en": "Commercial paper"},
    "DebtCurrent": {"es": "Deuda a corto plazo (parte corriente)", "en": "Debt (current)"},
    "LongTermDebtCurrent": {
        "es": "Deuda a largo plazo — parte corriente",
        "en": "Long-term debt (current portion)",
    },
    "AccountsPayableCurrent": {"es": "Proveedores", "en": "Accounts payable (current)"},
    "AccountsPayableAndAccruedLiabilitiesCurrent": {
        "es": "Proveedores y obligaciones devengadas",
        "en": "Accounts payable and accrued liabilities",
    },
    "AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent": {
        "es": "Proveedores y obligaciones devengadas (corriente y no corriente)",
        "en": "Accounts payable and accrued liabilities (current and non-current)",
    },
    "AccountsPayableAndOtherAccruedLiabilities": {
        "es": "Proveedores y otras obligaciones devengadas",
        "en": "Accounts payable and other accrued liabilities",
    },
    "AccruedLiabilitiesCurrent": {
        "es": "Obligaciones devengadas",
        "en": "Accrued liabilities (current)",
    },
    "OtherLiabilitiesCurrent": {"es": "Otros pasivos corrientes", "en": "Other current liabilities"},
    "ContractWithCustomerLiabilityCurrent": {
        "es": "Ingresos diferidos (contratos con clientes)",
        "en": "Contract liabilities (current)",
    },
    "DeferredRevenueCurrent": {"es": "Ingresos diferidos", "en": "Deferred revenue (current)"},
    # --- Non-current liabilities ----------------------------------------
    "LongTermDebtNoncurrent": {
        "es": "Deuda a largo plazo",
        "en": "Long-term debt (non-current)",
    },
    "DebtNoncurrent": {
        "es": "Deuda (no corriente)",
        "en": "Debt (non-current)",
    },
    "LongTermLiabilities": {
        "es": "Pasivo a largo plazo (total)",
        "en": "Long-term liabilities (total)",
    },
    "LongTermDebt": {"es": "Deuda a largo plazo", "en": "Long-term debt"},
    "OperatingLeaseLiabilityNoncurrent": {
        "es": "Pasivo por arrendamiento (operaciones)",
        "en": "Operating lease liabilities (non-current)",
    },
    "FinanceLeaseLiabilityNoncurrent": {
        "es": "Pasivo por arrendamiento (financiero)",
        "en": "Finance lease liabilities (non-current)",
    },
    "DeferredTaxLiabilitiesNoncurrent": {
        "es": "Pasivos fiscales diferidos",
        "en": "Deferred tax liabilities (non-current)",
    },
    "DeferredTaxLiabilitiesNet": {
        "es": "Pasivos fiscales diferidos (neto)",
        "en": "Deferred tax liabilities, net",
    },
    "OtherLiabilitiesNoncurrent": {
        "es": "Otros pasivos no corrientes",
        "en": "Other non-current liabilities",
    },
    # --- Equity ----------------------------------------------------------
    "PreferredStockValue": {"es": "Acciones preferentes", "en": "Preferred stock"},
    "CommonStockValue": {"es": "Acciones ordinarias", "en": "Common stock"},
    "CommonStocksIncludingAdditionalPaidInCapital": {
        "es": "Acciones ordinarias (incl. prima de emisión)",
        "en": "Common stock incl. additional paid-in capital",
    },
    "AdditionalPaidInCapital": {
        "es": "Prima de emisión",
        "en": "Additional paid-in capital",
    },
    "PaidInCapital": {"es": "Capital aportado", "en": "Paid-in capital"},
    "RetainedEarningsAccumulatedDeficit": {
        "es": "Resultados acumulados",
        "en": "Retained earnings (accumulated deficit)",
    },
    "RetainedEarnings": {"es": "Resultados acumulados", "en": "Retained earnings"},
    "TreasuryStockValue": {"es": "Tesorería (acciones propias)", "en": "Treasury stock"},
    "AccumulatedOtherComprehensiveIncomeLossNetOfTax": {
        "es": "Resultado integral acumulado",
        "en": "Accumulated other comprehensive income (loss)",
    },
    "MinorityInterest": {
        "es": "Intereses de control no incluidos",
        "en": "Minority interest",
    },
    # --- Memoranda (non-monetary) ----------------------------------------
    "CommonStockSharesOutstanding": {
        "es": "Acciones en circulación",
        "en": "Common shares outstanding",
    },
    "CommonStockSharesIssued": {
        "es": "Acciones emitidas",
        "en": "Common shares issued",
    },
    "CommonStockSharesAuthorized": {
        "es": "Acciones autorizadas",
        "en": "Common shares authorized",
    },
    "EntityCommonStockSharesOutstanding": {
        "es": "Acciones en circulación (portada)",
        "en": "Entity common shares outstanding (cover)",
    },
    "EntityPublicFloat": {
        "es": "Float público (capital flotante)",
        "en": "Public float",
    },
    "WeightedAverageNumberOfSharesOutstandingBasic": {
        "es": "Acciones medias (básico)",
        "en": "Weighted-average shares outstanding (basic)",
    },
    "WeightedAverageNumberOfSharesOutstanding": {
        "es": "Acciones medias",
        "en": "Weighted-average shares outstanding",
    },
    "WeightedAverageNumberOfSharesOutstandingDiluted": {
        "es": "Acciones medias (diluido)",
        "en": "Weighted-average shares outstanding (diluted)",
    },
    "WeightedAverageNumberOfDilutedSharesOutstanding": {
        "es": "Acciones medias diluidas",
        "en": "Weighted-average diluted shares outstanding",
    },
    "WeightedAverageNumberOfShareOutstandingBasicAndDiluted": {
        "es": "Acciones medias (básico y diluido)",
        "en": "Weighted-average shares outstanding (basic and diluted)",
    },
}


def label(concept: str, lang: str = "es") -> str:
    """Human label for a concept in ``lang`` (fallback: EN, then humanized)."""
    entry = FIELD_LABELS.get(concept)
    if entry:
        return entry.get(lang) or entry.get("en", "")
    return humanize_concept(concept)
