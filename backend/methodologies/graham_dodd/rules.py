"""Graham & Dodd rules with source references.

Every rule cites Security Analysis (Graham & Dodd, 1934) with page
numbers and era context.
"""

from __future__ import annotations

from backend.methodologies.base import Rule, SourceRef

_BOOK = "Security Analysis"
_EDITION = "1st ed. (Spanish translation)"
_YEAR = "1934"
_ERA = "1934"

_NWC_CAUTION = (
    "NWC test calibrated to Depression-era markets; "
    "rarely triggers today for large caps"
)
_COVERAGE_CAUTION = (
    "fixed-charge coverage examples are US railroads from 1934; "
    "capital-intensive industries may differ"
)


def _source(page: str, caution: str | None = None) -> SourceRef:
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page=page,
        era=_ERA,
        us_caution=caution,
    )


RULE_1_NWC = Rule(
    id="graham_dodd.rule_1_nwc",
    name="Net Working Capital Test",
    description="Price < 2/3 of net working capital per share",
    kind="EXPLICIT",
    source=_source("p. 5", _NWC_CAUTION),
)

RULE_2_FIXED_CHARGE_COVERAGE = Rule(
    id="graham_dodd.rule_2_fixed_charge_coverage",
    name="Fixed-Charge Coverage",
    description=(
        "Operating income covers interest expense >= 1.5x in at least "
        "5 of the last 6 years"
    ),
    kind="EXPLICIT",
    source=_source("p. 230", _COVERAGE_CAUTION),
)

RULE_3_EARNINGS_STABILITY = Rule(
    id="graham_dodd.rule_3_earnings_stability",
    name="Earnings Stability",
    description="Net income positive in at least 7 of the last 10 years",
    kind="EXPLICIT",
    source=_source("p. 101"),
)

RULE_4_BALANCE_SHEET_STRENGTH = Rule(
    id="graham_dodd.rule_4_balance_sheet_strength",
    name="Balance Sheet Strength",
    description="Total liabilities / total assets <= 0.5",
    kind="EXPLICIT",
    source=_source("p. 38, 41"),
)

RULE_5_MARGIN_OF_SAFETY = Rule(
    id="graham_dodd.rule_5_margin_of_safety",
    name="Margin of Safety",
    description=(
        "Qualitative: PASS if rule 1 suggests deep discount, "
        "WATCH if rule 1 fails but company is otherwise strong, "
        "FAIL if multiple quantitative rules fail"
    ),
    kind="EXPLICIT",
    source=_source("p. 5, 101"),
)

ALL_RULES = [
    RULE_1_NWC,
    RULE_2_FIXED_CHARGE_COVERAGE,
    RULE_3_EARNINGS_STABILITY,
    RULE_4_BALANCE_SHEET_STRENGTH,
    RULE_5_MARGIN_OF_SAFETY,
]
