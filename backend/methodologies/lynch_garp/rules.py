"""The five rules of the Lynch GARP (Growth At a Reasonable Price) screen.

Thresholds are from Peter Lynch's *One Up on Wall Street* (1989, Fireside
edition, with John Rothchild) and *Beating the Street* (1993). Rule 1 is the
central Lynch metric (the PEG ratio); rules 2-3 keep the growth story and the
balance sheet honest; rule 4 is Lynch's inventory watch; rule 5 is the
dividend-adjusted PEG from *Beating the Street*. Each rule carries a
:class:`SourceRef` with the era it was written for and the US-specific
caution that applies to it, per ``docs/methodology_decisions.md`` (Decision
6).

Only the first three rules count towards the verdict; rules 4 and 5 are
evaluated for confidence, score and red flags but never change the verdict.
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

_GROWTH_CAUTION = (
    "earnings-growth estimates vary by source and trailing window; PEG is "
    "only as good as the growth number fed into it"
)
_DEBT_CAUTION = (
    "NormalizedFinancials carries total_debt, used as a proxy for long-term "
    "debt (stricter than the book's long-term-debt-only comparison)"
)


def _one_up(page: str, caution: str | None = None) -> SourceRef:
    return SourceRef(
        book=_BOOK_ONE_UP,
        edition=_EDITION_ONE_UP,
        year=_YEAR_ONE_UP,
        page=page,
        era=_ERA,
        us_caution=caution or _GROWTH_CAUTION,
    )


def _beating(page: str, caution: str | None = None) -> SourceRef:
    return SourceRef(
        book=_BOOK_BEATING,
        edition=_EDITION_BEATING,
        year=_YEAR_BEATING,
        page=page,
        era=_ERA_BEATING,
        us_caution=caution or _GROWTH_CAUTION,
    )


RULE_1_PEG = Rule(
    id="lynch_garp.rule_1_peg",
    name="Reasonable P/E to Growth (PEG)",
    description=(
        "PEG = P/E divided by the earnings growth rate. PASS when PEG <= 1.0, "
        "WATCH when 1.0 < PEG <= 1.5, FAIL when PEG > 1.5 (paying too much "
        "for growth)."
    ),
    kind="EXPLICIT",
    source=_one_up("ch. on the perfect stock"),
)

RULE_2_GROWTH_CONSISTENCY = Rule(
    id="lynch_garp.rule_2_growth_consistency",
    name="Consistent Earnings Growth",
    description=(
        "EPS should have grown in at least 7 of the last 10 years (5-6 is a "
        "watch, fewer than 5 fails) — Lynch's stable-stalwart test."
    ),
    kind="EXPLICIT",
    source=_one_up("ch. on the stable stalwarts"),
)

RULE_3_DEBT_CONSERVATISM = Rule(
    id="lynch_garp.rule_3_debt_conservatism",
    name="Conservative Debt",
    description=(
        "Long-term debt should not exceed 2x net income (2-4x is a watch, "
        "above 4x fails)."
    ),
    kind="EXPLICIT",
    source=_one_up("ch. on the balance sheet", _DEBT_CAUTION),
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
    source=_one_up("ch. on checking the story"),
)

RULE_5_DIVIDEND_ADJUSTED_PEG = Rule(
    id="lynch_garp.rule_5_dividend_adjusted_peg",
    name="Dividend-Adjusted PEG (PEGY)",
    description=(
        "PEGY = PEG / (1 + dividend yield). Only evaluated for dividend "
        "payers; PASS when PEGY <= 1.0, WATCH to 1.5, FAIL above."
    ),
    kind="EXPLICIT",
    source=_beating("ch. on dividend-adjusted valuations"),
)

VERDICT_RULES = [
    RULE_1_PEG,
    RULE_2_GROWTH_CONSISTENCY,
    RULE_3_DEBT_CONSERVATISM,
]

ALL_RULES = VERDICT_RULES + [RULE_4_INVENTORY_VS_SALES, RULE_5_DIVIDEND_ADJUSTED_PEG]