"""Rule definitions for the ``fisher_quantitative_subset`` methodology.

Four of Philip Fisher's fifteen points (3, 5, 10, 13) are quantifiable from
financial statements; the other eleven need scuttlebutt and are out of scope
(docs/methodology_decisions.md, decision 1).
"""

from __future__ import annotations

from backend.methodologies.base import Rule, SourceRef

EDITION = "Wiley Investment Classics (reprint of 1996 revised ed.)"
YEAR = 1958
SUBJECT_CAUTION = (
    "The full Fisher method requires scuttlebutt; this is a quantitative subset only."
)


def _source(page: str) -> SourceRef:
    return SourceRef(
        book="Common Stocks and Uncommon Profits",
        edition=EDITION,
        year=YEAR,
        page=page,
        era="1958",
        us_caution=SUBJECT_CAUTION,
    )


RULES: list[Rule] = [
    Rule(
        id="fisher_quantitative_subset.rule_1_rnd_intensity",
        name="R&D intensity relative to size (point 3)",
        description=(
            "R&D spend as a share of sales; Fisher calls the ratio a 'crude yardstick'."
        ),
        kind="EXPLICIT",
        source=_source("54-55"),
    ),
    Rule(
        id="fisher_quantitative_subset.rule_2_profit_margin_quality",
        name="Worthwhile profit margin (point 5)",
        description=(
            "Operating profit per dollar of sales; avoid low-margin businesses."
        ),
        kind="EXPLICIT",
        source=_source("63-64"),
    ),
    Rule(
        id="fisher_quantitative_subset.rule_3_cost_control_stability",
        name="Cost analysis and accounting controls (point 10)",
        description=(
            "Management's cost breakdown and accounting controls; proxied by "
            "gross-margin stability."
        ),
        kind="EXPLICIT",
        source=_source("69"),
    ),
    Rule(
        id="fisher_quantitative_subset.rule_4_share_dilution",
        name="Growth without equity financing (point 13)",
        description=(
            "Growth financed from operations so the existing shareholder is "
            "not diluted."
        ),
        kind="EXPLICIT",
        source=_source("75"),
    ),
]

RULES_SOURCES = [rule.source for rule in RULES]

__all__ = ["RULES", "RULES_SOURCES"]
