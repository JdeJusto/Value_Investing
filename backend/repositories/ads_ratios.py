"""ADS ratios for common ADRs when the 20-F cover fact is absent.

``EntityListingDepositoryReceiptRatio`` is filed by some ADRs (BABA = 8) but
not all. These values come from the 20-F cover ("each ADS represents N
ordinary shares") and must be verified before adding a ticker. 1.0 means
1 ADS = 1 ordinary share; values below 1 mean N ADS = 1 ordinary share.
"""

from __future__ import annotations

#: ticker -> ordinary shares represented by one ADS.
ADS_RATIOS: dict[str, float] = {
    "BABA": 8.0,
    "BIDU": 8.0,
    "JD": 2.0,
    "PDD": 4.0,
    "TSM": 5.0,
    "TM": 10.0,
    "SNY": 0.5,
    "AZN": 0.5,
    "NIO": 1.0,
    "ASML": 1.0,
    "SAP": 1.0,
    "SHOP": 1.0,
    "BTI": 1.0,
}


def ads_ratio_for(ticker: str | None) -> float:
    """Fallback ADS ratio for a ticker (1.0 when unknown/not an ADR)."""
    if not ticker:
        return 1.0
    return ADS_RATIOS.get(str(ticker).upper(), 1.0)
