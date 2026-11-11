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

**The book was not available on this machine**
(``docs/books_notes/the-most-important-thing.md``). Every :class:`SourceRef`
therefore carries ``page="public knowledge"`` and a ``us_caution`` saying that
the rule is a public-knowledge reconstruction, not a quote or a page-level
paraphrase. See ``docs/marks_rules.md``.

In v2.0.0 these four rules are the legacy core of a weighted framework; the
deep checks live in :mod:`backend.methodologies.marks.deep_checks`.
"""

from __future__ import annotations

from backend.methodologies.base import Rule, SourceRef

_BOOK = "The Most Important Thing: Uncommon Sense for the Thoughtful Investor"
_EDITION = "1st edition"
_YEAR = 2011
_CAUTION = (
    "public-knowledge reconstruction, not from the book: the reference text "
    "was not available on this machine, so no quote, page number or "
    "page-level paraphrase is claimed; thresholds are public value and "
    "risk-control heuristics in the spirit of Marks' published writing"
)


def _source(note: str) -> SourceRef:
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page="public knowledge",
        era="2011",
        us_caution=f"{_CAUTION}; {note}",
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
    source=_source("company-level cycle proxy, not market timing"),
)

RULE_2_RESILIENCE = Rule(
    id="marks.rule_2_resilience",
    name="Resilience (preparedness)",
    description=(
        "Net debt / EBITDA <= 2.5, interest coverage >= 4x and positive free "
        "cash flow: the balance sheet can survive the down part of the cycle."
    ),
    kind="EXPLICIT",
    source=_source("survival-first balance-sheet test"),
)

RULE_3_MARGIN_OF_SAFETY = Rule(
    id="marks.rule_3_margin_of_safety",
    name="Margin of safety",
    description=(
        "FCF yield >= 4% or EV/EBIT <= 12: the price is below value rather "
        "than above it. Buying well is the first line of defence."
    ),
    kind="EXPLICIT",
    source=_source("price below value"),
)

RULE_4_QUALITY = Rule(
    id="marks.rule_4_quality_persistence",
    name="Quality persistence",
    description=(
        "Five-year average ROIC >= 10% with positive ROIC in at least four of "
        "the last five years: durable economics, not a lucky year."
    ),
    kind="EXPLICIT",
    source=_source("durable returns on capital"),
)

ALL_RULES = [
    RULE_1_CYCLE,
    RULE_2_RESILIENCE,
    RULE_3_MARGIN_OF_SAFETY,
    RULE_4_QUALITY,
]
