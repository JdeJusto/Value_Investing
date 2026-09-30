"""Screener eligibility: funds, trusts, ETFs and SPACs.

Most of the ~2,000 listed entities without a mapped revenue concept are
structurally revenue-less (funds, trusts, ETFs, SPACs — see
``docs/unmapped_coverage.md``). They clutter the screener and answer
INSUFFICIENT_DATA on every methodology, so they are excluded by default.

Two signals:

- **Data (primary)**: no revenue AND no net income in the last three fiscal
  years.
- **Name (secondary)**: a curated fund/trust/SPAC pattern, applied only when
  the company reports no revenue in the recent history — a bank called
  "Northern Trust" or an operating "Capital Corp" with real sales is never
  excluded by name alone.
"""

from __future__ import annotations

from typing import Any

#: Conservative, documented lower-case substrings of legal names.
FUND_OR_SPAC_NAME_PATTERNS = (
    " trust",
    "trust ",
    " fund",
    "fund ",
    " etf",
    "acquisition corp",
    "acquisition corporation",
    " spac",
    "blank check",
)

#: How many fiscal years count as "recent" for the data signal.
RECENT_YEARS = 3


def _name_matches(name: str | None) -> bool:
    if not name:
        return False
    lowered = name.lower()
    return any(pattern in lowered for pattern in FUND_OR_SPAC_NAME_PATTERNS)


def is_investable_company(
    row: Any, history: list | None = None, name: str | None = None
) -> bool:
    """False for entities that should not appear in screens by default.

    ``row`` is the latest :class:`NormalizedFinancials` (None = unknown, which
    is treated as investable so unexplained data is never hidden),
    ``history`` the year-desc list of rows and ``name`` the display name from
    the screener row (the VO carries no name).
    """
    if row is None:
        return True
    recent = list(history or [row])[:RECENT_YEARS]
    if any(getattr(r, "revenue", None) is not None for r in recent):
        return True
    if not any(getattr(r, "net_income", None) is not None for r in recent):
        return False
    # No revenue but a real bottom line: keep unless the name says fund/SPAC.
    return not _name_matches(name)
