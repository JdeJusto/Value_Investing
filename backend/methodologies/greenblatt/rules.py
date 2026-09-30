"""The three Greenblatt Magic Formula rules (*The Little Book That Beats the
Market*, 2005).

Rules 1 and 2 are the two ranking metrics (return on capital and earnings
yield); rule 3 is the combined rank that decides the verdict. All are
EXPLICIT rules from the book.
"""

from __future__ import annotations

from backend.methodologies.base import Rule, SourceRef

_BOOK = "The Little Book That Beats the Market"
_EDITION = "1st edition"
_YEAR = 2005
_CAUTION = (
    "cross-sectional by construction: a company's rank depends on the whole "
    "universe, so the ranking file must be refreshed periodically"
)


def _source(page: str) -> SourceRef:
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page=page,
        era="2005",
        us_caution=_CAUTION,
    )


RULE_1_ROC = Rule(
    id="greenblatt.rule_1_roc",
    name="Return on Capital",
    description=(
        "ROC = EBIT / (net working capital + net fixed assets), where net "
        "working capital is current assets minus current liabilities floored "
        "at zero and net fixed assets is net PPE. Companies are ranked by "
        "ROC (1 = best)."
    ),
    kind="EXPLICIT",
    source=_source("ch. 3, the Magic Formula"),
)

RULE_2_EY = Rule(
    id="greenblatt.rule_2_earnings_yield",
    name="Earnings Yield",
    description=(
        "EY = EBIT / Enterprise Value, where EV = market cap + total debt - "
        "cash. Companies are ranked by EY (1 = best)."
    ),
    kind="EXPLICIT",
    source=_source("ch. 3, the Magic Formula"),
)

RULE_3_RANK = Rule(
    id="greenblatt.rule_3_combined_rank",
    name="Combined Rank",
    description=(
        "combined_rank = rank_ROC + rank_EY; lower is better. Verdict by "
        "percentile: top 10% BUY, top 30% WATCH, top 50% HOLD, below AVOID."
    ),
    kind="EXPLICIT",
    source=_source("ch. 4, ranking the universe"),
)

ALL_RULES = [RULE_1_ROC, RULE_2_EY, RULE_3_RANK]
