"""Disaggregated expense lines from XBRL facts.

XBRL does not standardize "electricity" or "marketing" across filers. This
module maps the standardized subset that does exist and keeps undisclosed
lines explicit (``is_disclosed=False``), never 0. Per-ticker exceptions live
in :mod:`backend.repositories.expense_overrides`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Canonical line item -> candidate tags, in priority order.
EXPENSE_LINE_MAP: dict[str, tuple[str, ...]] = {
    "marketing": (
        "MarketingExpense",
        "AdvertisingExpense",
        "SellingAndMarketingExpense",
    ),
    "r_and_d": ("ResearchAndDevelopmentExpense",),
    "sga": ("SellingGeneralAndAdministrativeExpense",),
    "g_and_a": ("GeneralAndAdministrativeExpense",),
    "occupancy": ("OccupancyExpense",),
    "utilities": ("UtilitiesExpense",),
    "depreciation": ("DepreciationDepletionAndAmortization",),
}

#: Display labels, in table order.
EXPENSE_LINE_LABELS: dict[str, str] = {
    "marketing": "Marketing / advertising",
    "r_and_d": "Research & development",
    "sga": "Selling, general & administrative",
    "g_and_a": "General & administrative",
    "occupancy": "Occupancy",
    "utilities": "Utilities / electricity",
    "depreciation": "Depreciation & amortization",
}

EXPENSE_LINE_ORDER = tuple(EXPENSE_LINE_MAP)


@dataclass(frozen=True)
class ExpenseLine:
    """One canonical expense line for a ticker-year."""

    ticker: str
    fiscal_year: int
    line_item: str
    label: str
    value: float | None
    source: str
    is_disclosed: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "fiscal_year": self.fiscal_year,
            "line_item": self.line_item,
            "label": self.label,
            "value": self.value,
            "source": self.source,
            "is_disclosed": self.is_disclosed,
            "reason": self.reason,
        }


def _tag_source(fact: dict) -> str:
    namespace = str(fact.get("namespace") or "").strip()
    concept = str(fact.get("concept") or "").strip()
    return f"{namespace}:{concept}" if namespace else concept


def build_expense_lines(
    ticker: str,
    fiscal_year: int,
    facts: dict[str, dict],
    *,
    currency: str = "USD",
    fx_rate: float | None = None,
    overrides: dict[str, str | float | None] | None = None,
    not_applicable_reason: str | None = None,
) -> list[ExpenseLine]:
    """Pure assembly of the canonical lines from ``{concept: fact}``.

    ``fx_rate`` converts a non-USD monetary value to USD (the rate implied by
    core revenue). A missing rate leaves the value undisclosed, never mixed
    with USD. ``overrides`` may force a tag, a verified numeric value, or
    ``None`` (not disclosed).
    """
    overrides = overrides or {}
    lines: list[ExpenseLine] = []
    fx = fx_rate if fx_rate and fx_rate > 0 else None
    for line_item in EXPENSE_LINE_ORDER:
        label = EXPENSE_LINE_LABELS[line_item]
        if not_applicable_reason:
            lines.append(
                ExpenseLine(
                    ticker=ticker,
                    fiscal_year=fiscal_year,
                    line_item=line_item,
                    label=label,
                    value=None,
                    source="",
                    is_disclosed=False,
                    reason=not_applicable_reason,
                )
            )
            continue

        override = overrides.get(line_item)
        if override is None and line_item in overrides:
            lines.append(
                ExpenseLine(
                    ticker=ticker,
                    fiscal_year=fiscal_year,
                    line_item=line_item,
                    label=label,
                    value=None,
                    source=f"override:{ticker}",
                    is_disclosed=False,
                    reason="not disclosed in the filing (override)",
                )
            )
            continue
        if isinstance(override, (int, float)):
            lines.append(
                ExpenseLine(
                    ticker=ticker,
                    fiscal_year=fiscal_year,
                    line_item=line_item,
                    label=label,
                    value=float(override),
                    source=f"override:{ticker}",
                    is_disclosed=True,
                )
            )
            continue

        candidates = (
            (override,) if isinstance(override, str) else EXPENSE_LINE_MAP[line_item]
        )
        fact = next(
            (
                facts[tag]
                for tag in candidates
                if tag in facts and facts[tag].get("value") is not None
            ),
            None,
        )
        if fact is None:
            lines.append(
                ExpenseLine(
                    ticker=ticker,
                    fiscal_year=fiscal_year,
                    line_item=line_item,
                    label=label,
                    value=None,
                    source="",
                    is_disclosed=False,
                    reason="no XBRL tag",
                )
            )
            continue

        value = abs(float(fact["value"]))
        fact_currency = str(fact.get("currency") or currency or "USD").upper()
        if fact_currency != "USD":
            if fx is None:
                lines.append(
                    ExpenseLine(
                        ticker=ticker,
                        fiscal_year=fiscal_year,
                        line_item=line_item,
                        label=label,
                        value=None,
                        source=_tag_source(fact),
                        is_disclosed=False,
                        reason=f"FX rate unavailable ({fact_currency}→USD)",
                    )
                )
                continue
            value *= fx
        lines.append(
            ExpenseLine(
                ticker=ticker,
                fiscal_year=fiscal_year,
                line_item=line_item,
                label=label,
                value=value,
                source=_tag_source(fact),
                is_disclosed=True,
            )
        )
    return lines
