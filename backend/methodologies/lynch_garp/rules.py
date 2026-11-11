"""The five rules of the Lynch GARP (Growth At a Reasonable Price) screen.

The thresholds follow Peter Lynch's *One Up on Wall Street* (1989, with John
Rothchild) and *Beating the Street* (1993) as they are commonly published.
Rule 1 is the central Lynch metric (the PEG ratio); rules 2-3 keep the growth
story and the balance sheet honest; rule 4 is Lynch's inventory watch; rule 5
is the dividend-adjusted PEG.

**These books were not available on this machine**
(``docs/books_notes/one-up-on-wall-street.md``). Every :class:`SourceRef`
therefore carries ``page="public knowledge"`` and a ``us_caution`` saying that
the rule is a public-knowledge reconstruction, not a quote or a page-level
paraphrase. See ``docs/lynch_garp_rules.md``.

Only the first three rules are core; rules 4 and 5 are supporting checks. In
v2.0.0 every rule feeds the weighted verdict (``PASS`` counts as passed,
``WATCH``/``FAIL`` as not passed, ``INSUFFICIENT_DATA`` as missing).
"""

from __future__ import annotations

from backend.methodologies.base import Rule, SourceRef

_BOOK_ONE_UP = "One Up on Wall Street"
_EDITION_ONE_UP = "Fireside edition, with John Rothchild"
_YEAR_ONE_UP = 1989
_BOOK_BEATING = "Beating the Street"
_EDITION_BEATING = "1st edition, with John Rothchild"
_YEAR_BEATING = 1993
_ERA = "1989"
_ERA_BEATING = "1993"

_PUBLIC_CAUTION = (
    "public-knowledge reconstruction, not from the book: the reference text "
    "was not available on this machine, so no quote, page number or "
    "page-level paraphrase is claimed; thresholds are the published Lynch "
    "heuristics written for US markets in 1989-1993"
)
_GROWTH_CAUTION = (
    "earnings-growth estimates vary by source and trailing window; PEG is "
    "only as good as the growth number fed into it"
)
_DEBT_CAUTION = (
    "NormalizedFinancials carries total_debt, used as a proxy for long-term "
    "debt (stricter than the book's long-term-debt-only comparison)"
)


def _source(book: str, edition: str, year: int, era: str, note: str) -> SourceRef:
    return SourceRef(
        book=book,
        edition=edition,
        year=year,
        page="public knowledge",
        era=era,
        us_caution=f"{_PUBLIC_CAUTION}; {note}",
    )


def _one_up(note: str) -> SourceRef:
    return _source(_BOOK_ONE_UP, _EDITION_ONE_UP, _YEAR_ONE_UP, _ERA, note)


def _beating(note: str) -> SourceRef:
    return _source(_BOOK_BEATING, _EDITION_BEATING, _YEAR_BEATING, _ERA_BEATING, note)


RULE_1_PEG = Rule(
    id="lynch_garp.rule_1_peg",
    name="Reasonable P/E to Growth (PEG)",
    description=(
        "PEG = P/E divided by the earnings growth rate. PASS when PEG <= 1.0, "
        "WATCH when 1.0 < PEG <= 1.5, FAIL when PEG > 1.5 (paying too much "
        "for growth)."
    ),
    kind="EXPLICIT",
    source=_one_up(_GROWTH_CAUTION),
)

RULE_2_GROWTH_CONSISTENCY = Rule(
    id="lynch_garp.rule_2_growth_consistency",
    name="Consistent Earnings Growth",
    description=(
        "EPS should have grown in at least 7 of the last 10 years (5-6 is a "
        "watch, fewer than 5 fails) — the stable-stalwart consistency test."
    ),
    kind="EXPLICIT",
    source=_one_up("consistency of the earnings record"),
)

RULE_3_DEBT_CONSERVATISM = Rule(
    id="lynch_garp.rule_3_debt_conservatism",
    name="Conservative Debt",
    description=(
        "Long-term debt should not exceed 2x net income (2-4x is a watch, "
        "above 4x fails)."
    ),
    kind="EXPLICIT",
    source=_one_up(_DEBT_CAUTION),
)

RULE_4_INVENTORY_VS_SALES = Rule(
    id="lynch_garp.rule_4_inventory_vs_sales",
    name="Inventory Watch",
    description=(
        "Inventory should not grow faster than sales; growing more than 1.5x "
        "as fast as sales is a red flag. Companies that report no inventory "
        "(service, asset-light) are a watch with a note."
    ),
    kind="EXPLICIT",
    source=_one_up("inventory build as an early warning sign"),
)

RULE_5_DIVIDEND_ADJUSTED_PEG = Rule(
    id="lynch_garp.rule_5_dividend_adjusted_peg",
    name="Dividend-Adjusted PEG (PEGY)",
    description=(
        "PEGY = PEG / (1 + dividend yield). Only evaluated for dividend "
        "payers; PASS when PEGY <= 1.0, WATCH to 1.5, FAIL above."
    ),
    kind="EXPLICIT",
    source=_beating("dividend-adjusted valuation"),
)

VERDICT_RULES = [
    RULE_1_PEG,
    RULE_2_GROWTH_CONSISTENCY,
    RULE_3_DEBT_CONSERVATISM,
]

ALL_RULES = VERDICT_RULES + [RULE_4_INVENTORY_VS_SALES, RULE_5_DIVIDEND_ADJUSTED_PEG]
