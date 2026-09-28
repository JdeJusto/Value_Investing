"""Buffett/Clark rules with source references.

Every rule cites the book (Mary Buffett & David Clark, *Warren Buffett and
the Interpretation of Financial Statements*, 2001) with page numbers and
era context.
"""

from __future__ import annotations

from backend.methodologies.base import Rule, SourceRef

_BOOK = "Warren Buffett and the Interpretation of Financial Statements"
_EDITION = "1st ed. (Spanish translation)"
_YEAR = "2001"
_ERA = "2001"

_MARGIN_CAUTION = (
    "gross margin thresholds calibrated to US industrials; "
    "SaaS may structurally differ"
)
_INTEREST_CAUTION = (
    "interest burden examples are US airlines/tires from 2001; "
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


# ----------------------------------------------------------------------
# Rule 1 — Gross margin as moat proxy
# ----------------------------------------------------------------------
RULE_1_GROSS_MARGIN = Rule(
    id="buffett_clark.rule_1_gross_margin",
    name="Gross Margin ≥ 40%",
    description=(
        "Gross margin ≥ 40% indicates a durable competitive advantage; "
        "< 20% indicates a highly competitive industry."
    ),
    kind="EXPLICIT",
    source=_source("p. 55–56", _MARGIN_CAUTION),
)

# ----------------------------------------------------------------------
# Rule 2 — Interest coverage as DCA detector
# ----------------------------------------------------------------------
RULE_2_INTEREST_BURDEN = Rule(
    id="buffett_clark.rule_2_interest_burden",
    name="Interest Burden ≤ 10%",
    description=(
        "Interest expense ≤ 10% of operating income indicates a DCA company "
        "even inside competitive industries; ≥ 50% indicates capital-intensive "
        "or distressed."
    ),
    kind="EXPLICIT",
    source=_source("p. 73–74", _INTEREST_CAUTION),
)

# ----------------------------------------------------------------------
# Rule 3 — Gross margin durability
# ----------------------------------------------------------------------
RULE_3_MARGIN_DURABILITY = Rule(
    id="buffett_clark.rule_3_margin_durability",
    name="Gross Margin Durability",
    description=(
        "Gross margin must be stable or rising over many years; eroding "
        "margins mean the DCA is disappearing."
    ),
    kind="EXPLICIT",
    source=_source("p. 56"),
)

# ----------------------------------------------------------------------
# Rule 4 — Debt conservatism
# ----------------------------------------------------------------------
RULE_4_DEBT = Rule(
    id="buffett_clark.rule_4_debt",
    name="Low Long-Term Debt",
    description=(
        "Low long-term debt is a DCA indicator; high debt signals financial "
        "fragility."
    ),
    kind="EXPLICIT",
    source=_source("p. 38, 41"),
)

# ----------------------------------------------------------------------
# Rule 5 — Cash level
# ----------------------------------------------------------------------
RULE_5_CASH = Rule(
    id="buffett_clark.rule_5_cash",
    name="High Cash",
    description=(
        "High cash is a DCA indicator — the company does not need to borrow "
        "to operate."
    ),
    kind="EXPLICIT",
    source=_source("p. 41"),
)

# ----------------------------------------------------------------------
# Rule 6 — Capex relative to earnings
# ----------------------------------------------------------------------
RULE_6_CAPEX = Rule(
    id="buffett_clark.rule_6_capex",
    name="Low Capex",
    description=(
        "Low capital expenditure relative to earnings indicates a DCA company "
        "that does not need heavy reinvestment."
    ),
    kind="EXPLICIT",
    source=_source("p. 41"),
)

# ----------------------------------------------------------------------
# Rule 7 — Retained earnings growth
# ----------------------------------------------------------------------
RULE_7_RETAINED_EARNINGS = Rule(
    id="buffett_clark.rule_7_retained_earnings",
    name="Rising Retained Earnings",
    description=(
        "Rising retained earnings show the company is compounding value "
        "rather than paying it all out."
    ),
    kind="EXPLICIT",
    source=_source("p. 34"),
)

ALL_RULES = [
    RULE_1_GROSS_MARGIN,
    RULE_2_INTEREST_BURDEN,
    RULE_3_MARGIN_DURABILITY,
    RULE_4_DEBT,
    RULE_5_CASH,
    RULE_6_CAPEX,
    RULE_7_RETAINED_EARNINGS,
]
