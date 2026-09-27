"""The eight rules of the Graham defensive-investor screen.

Thresholds are verbatim from *The Intelligent Investor*, 4th revised edition
(1973) with Jason Zweig's commentary, Chapter 14 ("The Defensive Investor and
Common Stocks"). Each rule carries a :class:`SourceRef` with the era it was
written for and the US-specific caution that applies to it, per
``docs/methodology_decisions.md`` (Decision 6).

The first seven are the book's criteria; the eighth is the combined
P/E x P/BV <= 22.5 test from the same chapter, exposed both as a gate and as
a standalone metric (Decision 3).
"""

from __future__ import annotations

from backend.methodologies.base import Rule, SourceRef

_BOOK = "The Intelligent Investor"
_EDITION = "4th revised, with commentary by Jason Zweig"
_YEAR = 1973
_ERA = "1973"

# The size threshold is the one that needs era adjustment (Decision 4):
# $100M of 1973 sales is trivial in 2024 dollars.
_SIZE_CAUTION = "$100M in 1973 dollars; trivial in 2024 dollars"
_VALUATION_CAUTION = "15x and 1.5x are 1973 norms; see era_adjustment"


def _source(page: str, caution: str | None = None) -> SourceRef:
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page=page,
        era=_ERA,
        us_caution=caution,
    )


CRITERION_1_SIZE = Rule(
    id="graham.criterion_1_size",
    name="Adequate Size",
    description=(
        "Industrial companies must have at least $100M of annual sales; "
        "public utilities at least $50M of total assets."
    ),
    kind="EXPLICIT",
    source=_source("Ch. 14, criterion 1", _SIZE_CAUTION),
)

CRITERION_2_CURRENT_RATIO = Rule(
    id="graham.criterion_2_current_ratio",
    name="Strong Financial Condition",
    description=(
        "Current assets should be at least twice current liabilities "
        "(current ratio >= 2:1); long-term debt should not exceed net "
        "working capital (industrials)."
    ),
    kind="EXPLICIT",
    source=_source("Ch. 14, criterion 2"),
)

CRITERION_3_DEBT_VS_WORKING_CAPITAL = Rule(
    id="graham.criterion_3_debt_vs_working_capital",
    name="Debt Within Working Capital",
    description=(
        "Long-term debt must not be greater than net working capital "
        "(current assets minus current liabilities)."
    ),
    kind="EXPLICIT",
    source=_source("Ch. 14, criterion 2"),
)

CRITERION_4_DIVIDEND_HISTORY = Rule(
    id="graham.criterion_4_dividend_history",
    name="Dividend Record",
    description=(
        "Uninterrupted dividend payments for at least the last 20 years."
    ),
    kind="EXPLICIT",
    source=_source("Ch. 14, criterion 4"),
)

CRITERION_5_EARNINGS_GROWTH = Rule(
    id="graham.criterion_5_earnings_growth",
    name="Earnings Growth",
    description=(
        "An increase of at least one-third in earnings per share over the "
        "last ten years, using three-year averages of the endpoints."
    ),
    kind="EXPLICIT",
    source=_source("Ch. 14, criterion 5"),
)

CRITERION_6_PE = Rule(
    id="graham.criterion_6_pe",
    name="Moderate P/E",
    description=(
        "Current price should not exceed 15 times the average earnings of "
        "the last three years."
    ),
    kind="EXPLICIT",
    source=_source("Ch. 14, criterion 6", _VALUATION_CAUTION),
)

CRITERION_7_PBV = Rule(
    id="graham.criterion_7_pbv",
    name="Moderate Price/Book",
    description=(
        "Current price should not exceed 1.5 times the book value reported "
        "in the latest annual report."
    ),
    kind="EXPLICIT",
    source=_source("Ch. 14, criterion 7", _VALUATION_CAUTION),
)

CRITERION_8_PE_PBV_PRODUCT = Rule(
    id="graham.criterion_8_pe_pbv_product",
    name="Combined Valuation Test",
    description=(
        "The product of the P/E multiple and the price/book ratio should "
        "not exceed 22.5 (15 x 1.5). A higher P/E is allowed when the P/BV "
        "is correspondingly lower."
    ),
    kind="EXPLICIT",
    source=_source("Ch. 14, criterion 7", _VALUATION_CAUTION),
)

# The seven criteria that count towards the verdict (the eighth is the
# combined test, which is a gate on top of 6 and 7).
VERDICT_CRITERIA = [
    CRITERION_1_SIZE,
    CRITERION_2_CURRENT_RATIO,
    CRITERION_3_DEBT_VS_WORKING_CAPITAL,
    CRITERION_4_DIVIDEND_HISTORY,
    CRITERION_5_EARNINGS_GROWTH,
    CRITERION_6_PE,
    CRITERION_7_PBV,
]

ALL_RULES = VERDICT_CRITERIA + [CRITERION_8_PE_PBV_PRODUCT]
