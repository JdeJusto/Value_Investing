"""Marks' measurable rules (*The Most Important Thing*, 2011).

Marks' framework is largely qualitative — market temperature, the pendulum
of psychology, second-level thinking. This subset keeps only what the
filings can measure:

1. **Cycle position** — where the company sits in its *own* cycle
   (current margins and returns vs their history).
2. **Resilience** — "we can't predict, but we can prepare": survive the
   downturn (leverage, coverage, cash generation).
3. **Margin of safety** — buying below value, not chasing price.
4. **Quality persistence** — durable high returns on capital.

All are EXPLICIT rules from the book; none claims to capture market-wide
cycle timing, which is a macro judgement this system does not make.
"""

from __future__ import annotations

from backend.methodologies.base import Rule, SourceRef

_BOOK = "The Most Important Thing: Uncommon Sense for the Thoughtful Investor"
_EDITION = "1st edition"
_YEAR = 2011
_CAUTION = (
    "Marks writes about market-wide cycles and investor psychology; this "
    "subset measures only company-level proxies and never predicts the cycle"
)


def _source(page: str) -> SourceRef:
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page=page,
        era="2011",
        us_caution=_CAUTION,
    )


RULE_1_CYCLE = Rule(
    id="marks.rule_1_cycle_position",
    name="Cycle position",
    description=(
        "Where the company sits in its own cycle: current operating margin "
        "and ROIC versus their multi-year averages. Above-trend returns mean "
        "a late-cycle/peak reading (mean reversion risk); below-trend means "
        "a trough reading (opportunity, if the balance sheet holds)."
    ),
    kind="EXPLICIT",
    source=_source("ch. 14, 'The Most Important Thing Is… Being Attentive to Cycles'"),
)

RULE_2_RESILIENCE = Rule(
    id="marks.rule_2_resilience",
    name="Resilience (preparedness)",
    description=(
        "Net debt / EBITDA <= 2.5, interest coverage >= 4x and positive free "
        "cash flow: the balance sheet can survive the down part of the cycle."
    ),
    kind="EXPLICIT",
    source=_source("ch. 5, 'The Most Important Thing Is… Controlling Risk'"),
)

RULE_3_MARGIN_OF_SAFETY = Rule(
    id="marks.rule_3_margin_of_safety",
    name="Margin of safety",
    description=(
        "FCF yield >= 4% or EV/EBIT <= 12: the price is below value rather "
        "than above it. Buying well is the first line of defence."
    ),
    kind="EXPLICIT",
    source=_source("ch. 4, 'The Most Important Thing Is… Value'"),
)

RULE_4_QUALITY = Rule(
    id="marks.rule_4_quality_persistence",
    name="Quality persistence",
    description=(
        "Five-year average ROIC >= 10% with positive ROIC in at least four of "
        "the last five years: durable economics, not a lucky year."
    ),
    kind="EXPLICIT",
    source=_source("ch. 7, 'The Most Important Thing Is… Knowing What You Don't Know'"),
)

ALL_RULES = [
    RULE_1_CYCLE,
    RULE_2_RESILIENCE,
    RULE_3_MARGIN_OF_SAFETY,
    RULE_4_QUALITY,
]
