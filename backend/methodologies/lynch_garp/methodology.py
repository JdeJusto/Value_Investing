"""Lynch GARP (Growth At a Reasonable Price) methodology.

Peter Lynch's core quantitative screen from *One Up on Wall Street* (1989)
and *Beating the Street* (1993): buy growth at a reasonable multiple, not
growth at any price. The central metric is the PEG ratio (P/E divided by the
earnings growth rate); the supporting rules keep the growth story honest
(consistency), the balance sheet conservative (debt), the operating story
coherent (inventory watching sales) and the valuation dividend-aware.

The methodology receives already-fetched fundamentals and prices and never
touches the network or the database, so it is deterministic and testable.

Known limitations (see ``README.md``):
- written for product companies; financials do not fit the inventory rule or
  the debt model;
- the growth rate is a geometric CAGR over the available earnings history and
  its precision depends on the source and span of the data;
- companies are categorized into Lynch's six types (fast grower, stalwart,
  slow grower, cyclical, turnaround, asset play) from growth, dividends,
  sector and market cap; when those inputs are missing the category falls
  back to UNKNOWN and the generic PEG screen applies.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import (
    Confidence,
    Methodology,
    MethodologyResult,
    Verdict,
)
from backend.methodologies.common.company_type import (
    financial_na_reason,
    is_financial,
)
from backend.methodologies.common.ratio_guards import (
    is_meaningful_pbv,
    is_meaningful_pe,
)
from backend.methodologies.lynch_garp.rules import (
    ALL_RULES,
    RULE_1_PEG,
    RULE_5_DIVIDEND_ADJUSTED_PEG,
    VERDICT_RULES,
)

# Verbatim thresholds from the books.
_PEG_PASS = 1.0
_PEG_WATCH = 1.5
_MIN_GROWTH_YEARS = 7
_WATCH_GROWTH_YEARS = 5
_DEBT_PASS = 2.0
_DEBT_WATCH = 4.0
_INVENTORY_WATCH_FACTOR = 1.5
#: Fast growers get a stricter inventory watch (any faster growth flags sooner).
_FAST_GROWER_INVENTORY_FACTOR = 1.25

# Lynch category thresholds (One Up on Wall Street, ch. 6, "The Six
# Categories"). A company is typed by the first rule that matches, in the
# precedence order documented in the README.
_STALWART_MARKET_CAP = 10_000_000_000.0
_FAST_GROWER_CAGR = 0.20
_HYPER_GROWTH_CAGR = 0.30
_HYPER_GROWTH_PEG_PREMIUM = 0.2
_SLOW_GROWER_CAGR = 0.08
#: Lynch's cyclical sectors, matched as case-insensitive substrings so provider
#: label variants ("Materials", "Industrials—Diversified", "Oil & Gas",
#: "Consumer Discretionary") and casing differences keep resolving. The exact
#: set (Basic Materials / Energy / Industrials / Consumer Cyclical) is a subset.
_CYCLICAL_SECTOR_KEYWORDS = (
    "basic material",
    "material",
    "energy",
    "oil",
    "gas",
    "industrial",
    "capital goods",
    "consumer cyclical",
    "consumer discretionary",
    "cyclical",
    "automotive",
    "semiconductor",
    "mining",
    "steel",
    "chemical",
)
_CYCLICAL_VOLATILITY = 0.5
_ASSET_PLAY_PBV = 0.7
_DIVIDEND_STABILITY_PASS = 9
_DIVIDEND_STABILITY_WATCH = 7
_CATEGORY_YEARS = 5

_PASS = "PASS"
_WATCH = "WATCH"
_FAIL = "FAIL"
_INSUFFICIENT = "INSUFFICIENT_DATA"

_FLAG_BY_RULE = {
    "lynch_garp.rule_1_peg": "PEG above 1.5 (paying too much for growth)",
    "lynch_garp.rule_2_growth_consistency": (
        "Earnings declined in 4+ of the last 10 years"
    ),
    "lynch_garp.rule_3_debt_conservatism": "Long-term debt above 4x net income",
    "lynch_garp.rule_4_inventory_vs_sales": ("Inventory growing 50% faster than sales"),
    "lynch_garp.rule_5_dividend_adjusted_peg": ("Dividend-adjusted PEG above 1.5"),
}


def _is_cyclical_sector(sector: Any) -> bool:
    """True when a sector label reads as cyclical (case-insensitive substring).

    A single provider variant ("Materials", "Industrials—Diversified") used to
    drop a volatile company out of the Cyclical bucket and into a growth one;
    matching keywords instead of an exact set removes that silent fallback.
    """
    if not sector:
        return False
    lowered = str(sector).strip().lower()
    return any(keyword in lowered for keyword in _CYCLICAL_SECTOR_KEYWORDS)


@dataclass(frozen=True)
class RuleOutcome:
    """Outcome of one rule: PASS, WATCH, FAIL or INSUFFICIENT_DATA."""

    rule_id: str
    outcome: str
    value: float | None = None
    threshold: float | None = None
    detail: str = ""


class LynchCategory(str, Enum):
    """Lynch's six company types (One Up on Wall Street, ch. 6)."""

    SLOW_GROWER = "SLOW_GROWER"
    STALWART = "STALWART"
    FAST_GROWER = "FAST_GROWER"
    CYCLICAL = "CYCLICAL"
    TURNAROUND = "TURNAROUND"
    ASSET_PLAY = "ASSET_PLAY"
    UNKNOWN = "UNKNOWN"


#: Human labels for the CLI and reports.
CATEGORY_LABELS = {
    LynchCategory.SLOW_GROWER: "Slow Grower (mature, dividend-focused)",
    LynchCategory.STALWART: "Stalwart (large-cap, moderate growth)",
    LynchCategory.FAST_GROWER: "Fast Grower (aggressive growth)",
    LynchCategory.CYCLICAL: "Cyclical (follows the economic cycle)",
    LynchCategory.TURNAROUND: "Turnaround (beaten-down recovery)",
    LynchCategory.ASSET_PLAY: "Asset Play (hidden asset value)",
    LynchCategory.UNKNOWN: "Unclassified",
}

#: Short labels for CSV export (UI keeps the long labels from CATEGORY_LABELS).
CATEGORY_SHORT = {
    LynchCategory.SLOW_GROWER: "Slow Grower",
    LynchCategory.STALWART: "Stalwart",
    LynchCategory.FAST_GROWER: "Fast Grower",
    LynchCategory.CYCLICAL: "Cyclical",
    LynchCategory.TURNAROUND: "Turnaround",
    LynchCategory.ASSET_PLAY: "Asset Play",
    LynchCategory.UNKNOWN: "Unknown",
}

#: Categories whose Rule 1 is not the PEG: the generic passed/evaluable score
#: is not comparable across categories, so it is hidden (never invented).
_SCORELESS_CATEGORIES = frozenset({LynchCategory.SLOW_GROWER, LynchCategory.ASSET_PLAY})
_SCORE_NOTES = {
    LynchCategory.SLOW_GROWER: (
        "Score not applicable for Slow Grower; the verdict is based on "
        "dividend stability and margin stability."
    ),
    LynchCategory.ASSET_PLAY: (
        "Score not applicable for Asset Play; the verdict is based on the "
        "price-to-book discount."
    ),
}


class LynchGARPMethodology(Methodology):
    """The GARP screen, as a self-contained book methodology."""

    name = "lynch_garp"
    version = "1.2.0"
    family = "GARP"

    # ------------------------------------------------------------------
    # Methodology ABC
    # ------------------------------------------------------------------
    def evaluate(
        self,
        ticker: str,
        fundamentals: Any,
        prices: Any,
    ) -> MethodologyResult:
        rows = self._clean_rows(fundamentals)
        price = self._current_price(ticker, prices)

        latest = rows[0] if rows else None
        if is_financial(latest, getattr(latest, "sector", None)):
            financial_reason = (
                "Lynch GARP rules do not apply to financial companies "
                "(banks, insurers). Debt and inventory rules are "
                "structurally different. See README for details."
            )
            na_reason = financial_na_reason(
                latest, rows, getattr(latest, "sector", None), ticker
            )
            return MethodologyResult(
                methodology=self.name,
                version=self.version,
                family=self.family,
                verdict=Verdict.NOT_APPLICABLE,
                score=None,
                metrics={
                    "financial_company": True,
                    "rule_outcomes": {},
                    "current_price": price,
                    "fiscal_years_analyzed": len(rows),
                },
                reasons=[
                    financial_reason,
                    na_reason,
                    f"verdict: {Verdict.NOT_APPLICABLE.value}",
                ],
                red_flags=[],
                confidence=Confidence.HIGH,
                sources=[rule.source for rule in ALL_RULES],
                passed_rules=[],
                failed_rules=[],
            )

        market_cap = self._market_cap(ticker, prices, latest, price)
        category = self._categorize(rows, market_cap)
        criterion = self._rule_1_criterion(category)
        revenue_cagr = self._revenue_cagr(rows)
        peg_premium = 0.0
        if (
            category is LynchCategory.FAST_GROWER
            and revenue_cagr is not None
            and revenue_cagr > _HYPER_GROWTH_CAGR
        ):
            peg_premium = _HYPER_GROWTH_PEG_PREMIUM
        inventory_factor = (
            _FAST_GROWER_INVENTORY_FACTOR
            if category is LynchCategory.FAST_GROWER
            else _INVENTORY_WATCH_FACTOR
        )

        if category is LynchCategory.SLOW_GROWER:
            rule_1 = self._rule_1_dividend_stability(rows)
        elif category is LynchCategory.ASSET_PLAY:
            rule_1 = self._rule_1_price_to_book(rows, market_cap)
        elif category is LynchCategory.TURNAROUND:
            rule_1 = self._rule_1_peg(rows, price, relax_negative_growth=True)
        else:
            rule_1 = self._rule_1_peg(rows, price, premium=peg_premium)

        outcomes = [
            rule_1,
            self._rule_2_growth_consistency(rows),
            self._rule_3_debt_conservatism(rows),
            self._rule_4_inventory_vs_sales(rows, factor=inventory_factor),
            self._rule_5_dividend_adjusted_peg(rows, price),
        ]

        verdict, score, confidence = self._verdict(category, outcomes, rows)
        if category in _SCORELESS_CATEGORIES:
            # Rule 1 is not the PEG for these categories; the generic
            # passed/evaluable score is not comparable and is hidden rather
            # than invented (the verdict + category carry the judgment).
            score = None
        red_flags = self._red_flags(outcomes)
        reasons = self._reasons(outcomes, verdict, category)

        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=score,
            metrics=self._metrics(outcomes, price, rows, category, criterion),
            reasons=reasons,
            red_flags=red_flags,
            confidence=confidence,
            sources=[rule.source for rule in ALL_RULES],
            passed_rules=[o.rule_id for o in outcomes if o.outcome == _PASS],
            failed_rules=[o.rule_id for o in outcomes if o.outcome == _FAIL],
        )

    def rules(self) -> list:
        return list(ALL_RULES)

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "label": self.name,
            "version": self.version,
            "family": self.family,
            "source": ("One Up on Wall Street (1989); Beating the Street (1993)"),
            "known_limitations": [
                (
                    "does not apply to financials (no inventory line; different "
                    "debt model)"
                ),
                (
                    "growth-rate estimation depends on the source and span of the "
                    "earnings CAGR"
                ),
                (
                    "companies are categorized (fast grower, stalwart, slow "
                    "grower, cyclical, turnaround, asset play) from growth, "
                    "dividends, sector and market cap; missing inputs fall back "
                    "to UNKNOWN and the generic PEG screen"
                ),
                (
                    "rule 3 prefers long_term_debt, falling back to total_debt "
                    "(stricter than the book's long-term-debt-only comparison)"
                ),
                (
                    "rule 4 reads the optional inventory field; companies that "
                    "report no inventory get a WATCH with a note"
                ),
            ],
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_rows(fundamentals: Any) -> list[NormalizedFinancials]:
        rows = [r for r in (fundamentals or []) if r is not None]
        rows.sort(key=lambda r: r.fiscal_year, reverse=True)
        return rows

    @staticmethod
    def _current_price(ticker: str, prices: Any) -> float | None:
        getter = getattr(prices, "get_current_price", None)
        if not callable(getter):
            return None
        try:
            value = getter(ticker)
        except Exception:  # noqa: BLE001 — no price is not an error
            return None
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _earnings_cagr(rows: list[NormalizedFinancials]) -> float | None:
        """Geometric CAGR of net income over the available profitable years."""
        profit = sorted(
            [r for r in rows if r.net_income is not None and r.net_income > 0],
            key=lambda r: r.fiscal_year,
        )
        if len(profit) < 2:
            return None
        start = profit[0].net_income
        end = profit[-1].net_income
        years = profit[-1].fiscal_year - profit[0].fiscal_year
        if start <= 0 or end <= 0 or years <= 0:
            return None
        return (end / start) ** (1.0 / years) - 1.0

    @staticmethod
    def _eps(row: NormalizedFinancials) -> float | None:
        if row is None or row.net_income is None or (row.shares_outstanding or 0) <= 0:
            return None
        return row.net_income / row.shares_outstanding

    # ------------------------------------------------------------------
    # categorization (One Up on Wall Street, ch. 6)
    # ------------------------------------------------------------------
    @staticmethod
    def _market_cap(ticker, prices, latest, price) -> float | None:
        """Market cap from the price service, else price x shares."""
        getter = getattr(prices, "get_market_cap", None)
        if callable(getter):
            try:
                value = getter(ticker)
                if value is not None:
                    return float(value)
            except Exception:  # noqa: BLE001, S110 — no market cap is not an error
                pass
        if (
            price is not None
            and latest is not None
            and (latest.shares_outstanding or 0) > 0
        ):
            return float(price) * float(latest.shares_outstanding)
        return None

    @staticmethod
    def _revenue_cagr(rows, years: int = _CATEGORY_YEARS) -> float | None:
        """Revenue CAGR over the newest-to-oldest span within ``years``."""
        with_rev = [r for r in rows if r.revenue is not None and r.revenue > 0]
        if len(with_rev) < 2:
            return None
        newest = with_rev[0]
        window = [r for r in with_rev if newest.fiscal_year - r.fiscal_year <= years]
        oldest = window[-1]
        span = newest.fiscal_year - oldest.fiscal_year
        if span <= 0:
            return None
        return (newest.revenue / oldest.revenue) ** (1.0 / span) - 1.0

    @staticmethod
    def _eps_positive_years(rows, years: int = _CATEGORY_YEARS) -> int:
        """Newest ``years`` fiscal years with positive earnings per share."""
        count = 0
        for row in rows[:years]:
            eps = LynchGARPMethodology._eps(row)
            if eps is not None and eps > 0:
                count += 1
        return count

    @staticmethod
    def _net_margin(row) -> float | None:
        """Net income / revenue for one row, or None when not computable."""
        if (
            row is None
            or row.revenue is None
            or row.revenue <= 0
            or row.net_income is None
        ):
            return None
        return row.net_income / row.revenue

    @staticmethod
    def _dividend_years(rows, years: int) -> int:
        """Fiscal years (newest first) with a dividend paid, within the window."""
        return sum(1 for r in rows[:years] if (r.dividends_paid or 0) > 0)

    @staticmethod
    def _non_declining_dividends(rows, years: int = _CATEGORY_YEARS) -> int:
        """Comparisons (up to ``years``) where the dividend did not decline."""
        window = list(reversed(rows[: years + 1]))  # oldest -> newest
        values = [r.dividends_paid for r in window]
        return sum(
            1
            for i in range(1, len(values))
            if values[i] is not None
            and values[i - 1] is not None
            and values[i] >= values[i - 1]
        )

    @staticmethod
    def _net_margin_stable(rows, years: int = _CATEGORY_YEARS) -> bool:
        """Latest net margin is not materially below the window's average."""
        margins = [
            r.net_income / r.revenue
            for r in rows[:years]
            if r.revenue is not None and r.revenue > 0 and r.net_income is not None
        ]
        if not margins:
            return False
        return margins[0] >= statistics.fmean(margins) - 0.01

    @staticmethod
    def _is_improving(rows) -> bool:
        """Latest net income is positive or at least trending up."""
        latest = rows[0].net_income if rows else None
        if latest is None:
            return False
        if latest > 0:
            return True
        prev = rows[1].net_income if len(rows) > 1 else None
        return prev is not None and latest > prev

    @staticmethod
    def _earnings_volatility(rows, years: int = 10) -> float | None:
        """Stdev / |mean| of net income over the newest ``years``."""
        values = [r.net_income for r in rows[:years] if r.net_income is not None]
        if len(values) < 4:
            return None
        mean = statistics.fmean(values)
        if mean == 0:
            return None
        return statistics.pstdev(values) / abs(mean)

    def _is_cyclical(self, sector, rows) -> bool:
        """Cyclical sector plus volatile earnings (Lynch's warning sign).

        Sector matching is case-insensitive and keyword-based so provider
        label variants resolve; a missing or non-cyclical sector never
        fabricates the category.
        """
        if not _is_cyclical_sector(sector):
            return False
        volatility = self._earnings_volatility(rows)
        return volatility is not None and volatility > _CYCLICAL_VOLATILITY

    def _is_asset_play(self, rows, market_cap) -> bool:
        """Deep discount to book value, without compounder-grade growth."""
        latest = rows[0] if rows else None
        if latest is None or market_cap is None or market_cap <= 0:
            return False
        book = getattr(latest, "stockholders_equity", None)
        if book is None or book <= 0:
            return False
        growth = self._earnings_cagr(rows)
        if growth is not None and growth >= _FAST_GROWER_CAGR:
            return False
        return (market_cap / book) < _ASSET_PLAY_PBV

    def _categorize(self, rows, market_cap) -> LynchCategory:
        """Lynch's six categories; the first matching rule wins.

        Precedence: Turnaround > Fast Grower > Cyclical > Asset Play >
        Stalwart > Slow Grower > UNKNOWN. Missing inputs never fabricate a
        category: the company falls through to UNKNOWN and the generic PEG
        screen applies.

        Fast Grower follows Lynch's classic criterion — a small/aggressive
        company growing 20-25% a year — with no size gate at all: any
        company with revenue CAGR >= 20%, positive EPS in >= 4 of 5 years
        and a positive net margin is a Fast Grower, large cap or not
        (TSLA, NVDA included). ``market_cap`` is still used to tell
        Stalwarts and Slow Growers (large, slower) apart.
        """
        latest = rows[0] if rows else None
        if latest is None:
            return LynchCategory.UNKNOWN
        revenue_cagr = self._revenue_cagr(rows)
        margin = self._net_margin(latest)
        negative_years = sum(
            1 for r in rows[:_CATEGORY_YEARS] if (r.net_income or 0) < 0
        )
        positive_years = sum(
            1 for r in rows[:_CATEGORY_YEARS] if (r.net_income or 0) > 0
        )
        sector = getattr(latest, "sector", None)

        if negative_years >= 2 and self._is_improving(rows):
            return LynchCategory.TURNAROUND
        if (
            revenue_cagr is not None
            and revenue_cagr >= _FAST_GROWER_CAGR
            and self._eps_positive_years(rows) >= _CATEGORY_YEARS - 1
            and margin is not None
            and margin > 0.0
        ):
            return LynchCategory.FAST_GROWER
        if self._is_cyclical(sector, rows):
            return LynchCategory.CYCLICAL
        if self._is_asset_play(rows, market_cap):
            return LynchCategory.ASSET_PLAY
        if (
            revenue_cagr is not None
            and _SLOW_GROWER_CAGR <= revenue_cagr < _FAST_GROWER_CAGR
            and market_cap is not None
            and market_cap >= _STALWART_MARKET_CAP
            and positive_years >= _CATEGORY_YEARS - 1
        ):
            return LynchCategory.STALWART
        if (
            revenue_cagr is not None
            and 0.0 <= revenue_cagr < _SLOW_GROWER_CAGR
            and self._dividend_years(rows, _CATEGORY_YEARS) >= _CATEGORY_YEARS
            and market_cap is not None
            and market_cap >= _STALWART_MARKET_CAP
        ):
            return LynchCategory.SLOW_GROWER
        return LynchCategory.UNKNOWN

    @staticmethod
    def _rule_1_criterion(category: LynchCategory) -> str:
        """Which criterion replaced rule 1's PEG for this category."""
        if category is LynchCategory.SLOW_GROWER:
            return "dividend_stability"
        if category is LynchCategory.ASSET_PLAY:
            return "price_to_book"
        if category is LynchCategory.TURNAROUND:
            return "turnaround_peg"
        return "peg"

    # ------------------------------------------------------------------
    # the five rules
    # ------------------------------------------------------------------
    def _rule_1_peg(
        self,
        rows,
        price: float | None,
        premium: float = 0.0,
        relax_negative_growth: bool = False,
    ) -> RuleOutcome:
        pass_level = _PEG_PASS + premium
        watch_level = _PEG_WATCH + premium
        if price is None:
            return RuleOutcome(
                RULE_1_PEG.id,
                _INSUFFICIENT,
                None,
                pass_level,
                "no live price available",
            )
        latest = rows[0] if rows else None
        eps = self._eps(latest)
        if eps is None or eps <= 0:
            return RuleOutcome(
                RULE_1_PEG.id,
                _INSUFFICIENT,
                None,
                pass_level,
                "no earnings or share count",
            )
        pe = price / eps
        if not is_meaningful_pe(pe):
            return RuleOutcome(
                RULE_1_PEG.id,
                _FAIL,
                pe,
                pass_level,
                f"P/E {pe:.1f} is not meaningful (loss or extreme)",
            )
        growth = self._earnings_cagr(rows)
        if growth is None:
            return RuleOutcome(
                RULE_1_PEG.id,
                _INSUFFICIENT,
                None,
                pass_level,
                "no earnings-growth series (needs 2+ profitable years)",
            )
        if growth <= 0:
            if relax_negative_growth:
                return RuleOutcome(
                    RULE_1_PEG.id,
                    _INSUFFICIENT,
                    None,
                    pass_level,
                    (
                        f"turnaround: earnings still recovering ({growth:+.1%}) "
                        "— PEG not meaningful"
                    ),
                )
            return RuleOutcome(
                RULE_1_PEG.id,
                _FAIL,
                None,
                pass_level,
                f"PEG undefined: earnings growth {growth:+.1%}",
            )
        peg = pe / (growth * 100.0)
        detail = f"PEG {peg:.2f} (P/E {pe:.1f} / growth {growth:.1%})"
        if premium > 0:
            detail += f" — fast-grower premium +{premium:.1f}"
        if peg <= pass_level:
            return RuleOutcome(RULE_1_PEG.id, _PASS, peg, pass_level, detail)
        if peg <= watch_level:
            return RuleOutcome(RULE_1_PEG.id, _WATCH, peg, watch_level, detail)
        return RuleOutcome(RULE_1_PEG.id, _FAIL, peg, watch_level, detail)

    def _rule_1_dividend_stability(self, rows) -> RuleOutcome:
        """Rule 1 for slow growers: dividend stability instead of PEG.

        PASS when the dividend was paid in >= 9 of the last 10 years, WATCH
        for 7-8, FAIL below. Lynch does not ask a slow grower for growth.
        """
        if len(rows) < 10:
            return RuleOutcome(
                RULE_1_PEG.id,
                _INSUFFICIENT,
                None,
                float(_DIVIDEND_STABILITY_PASS),
                "needs 10 fiscal years of dividend history",
            )
        paid = self._dividend_years(rows, 10)
        detail = f"dividend paid in {paid} of 10 years (slow grower: PEG not required)"
        if paid >= _DIVIDEND_STABILITY_PASS:
            return RuleOutcome(
                RULE_1_PEG.id,
                _PASS,
                float(paid),
                float(_DIVIDEND_STABILITY_PASS),
                detail,
            )
        if paid >= _DIVIDEND_STABILITY_WATCH:
            return RuleOutcome(
                RULE_1_PEG.id,
                _WATCH,
                float(paid),
                float(_DIVIDEND_STABILITY_WATCH),
                detail,
            )
        return RuleOutcome(
            RULE_1_PEG.id, _FAIL, float(paid), float(_DIVIDEND_STABILITY_WATCH), detail
        )

    def _rule_1_price_to_book(self, rows, market_cap) -> RuleOutcome:
        """Rule 1 for asset plays: P/BV instead of PEG.

        PASS when P/BV < 0.7, WATCH below 1.0, FAIL at/above 1.0.
        """
        latest = rows[0] if rows else None
        book = getattr(latest, "stockholders_equity", None) if latest else None
        if market_cap is None or market_cap <= 0 or book is None or book <= 0:
            return RuleOutcome(
                RULE_1_PEG.id,
                _INSUFFICIENT,
                None,
                _ASSET_PLAY_PBV,
                "no market cap or book value for the P/BV rule",
            )
        pbv = market_cap / book
        if not is_meaningful_pbv(pbv):
            return RuleOutcome(
                RULE_1_PEG.id,
                _FAIL,
                pbv,
                _ASSET_PLAY_PBV,
                f"P/BV {pbv:.2f} is not meaningful (extreme book ratio)",
            )
        detail = f"P/BV {pbv:.2f} (asset play: book value vs market cap)"
        if pbv < _ASSET_PLAY_PBV:
            return RuleOutcome(RULE_1_PEG.id, _PASS, pbv, _ASSET_PLAY_PBV, detail)
        if pbv < 1.0:
            return RuleOutcome(RULE_1_PEG.id, _WATCH, pbv, _ASSET_PLAY_PBV, detail)
        return RuleOutcome(RULE_1_PEG.id, _FAIL, pbv, _ASSET_PLAY_PBV, detail)

    def _rule_2_growth_consistency(self, rows) -> RuleOutcome:
        if len(rows) < 10:
            return RuleOutcome(
                "lynch_garp.rule_2_growth_consistency",
                _INSUFFICIENT,
                None,
                float(_MIN_GROWTH_YEARS),
                "needs 10 fiscal years",
            )
        ordered = sorted(rows, key=lambda r: r.fiscal_year)[-10:]
        eps_list = [self._eps(r) for r in ordered]
        comparisons = [
            eps_list[i] > eps_list[i - 1]
            for i in range(1, len(eps_list))
            if eps_list[i] is not None and eps_list[i - 1] is not None
        ]
        if len(comparisons) < 9:
            return RuleOutcome(
                "lynch_garp.rule_2_growth_consistency",
                _INSUFFICIENT,
                None,
                float(_MIN_GROWTH_YEARS),
                "no year-over-year EPS comparisons available",
            )
        grew = sum(1 for c in comparisons if c)
        detail = f"EPS grew in {grew} of {len(comparisons)} year-over-year comparisons"
        if grew >= _MIN_GROWTH_YEARS:
            return RuleOutcome(
                "lynch_garp.rule_2_growth_consistency",
                _PASS,
                float(grew),
                float(_MIN_GROWTH_YEARS),
                detail,
            )
        if grew >= _WATCH_GROWTH_YEARS:
            return RuleOutcome(
                "lynch_garp.rule_2_growth_consistency",
                _WATCH,
                float(grew),
                float(_MIN_GROWTH_YEARS),
                detail,
            )
        return RuleOutcome(
            "lynch_garp.rule_2_growth_consistency",
            _FAIL,
            float(grew),
            float(_MIN_GROWTH_YEARS),
            detail,
        )

    def _rule_3_debt_conservatism(self, rows) -> RuleOutcome:
        latest = rows[0] if rows else None
        if latest is None or latest.net_income is None or latest.net_income <= 0:
            return RuleOutcome(
                "lynch_garp.rule_3_debt_conservatism",
                _INSUFFICIENT,
                None,
                _DEBT_PASS,
                "net income is not positive",
            )
        debt = latest.long_term_debt
        if debt is None:
            debt = latest.total_debt
        if debt is None:
            return RuleOutcome(
                "lynch_garp.rule_3_debt_conservatism",
                _INSUFFICIENT,
                None,
                _DEBT_PASS,
                "no debt data",
            )
        ratio = debt / latest.net_income
        detail = (
            f"debt / net income {ratio:.2f} (long-term debt, falling back "
            "to total_debt when it is not reported)"
        )
        if ratio <= _DEBT_PASS:
            return RuleOutcome(
                "lynch_garp.rule_3_debt_conservatism",
                _PASS,
                ratio,
                _DEBT_PASS,
                detail,
            )
        if ratio <= _DEBT_WATCH:
            return RuleOutcome(
                "lynch_garp.rule_3_debt_conservatism",
                _WATCH,
                ratio,
                _DEBT_WATCH,
                detail,
            )
        return RuleOutcome(
            "lynch_garp.rule_3_debt_conservatism",
            _FAIL,
            ratio,
            _DEBT_WATCH,
            detail,
        )

    def _rule_4_inventory_vs_sales(
        self, rows, factor: float = _INVENTORY_WATCH_FACTOR
    ) -> RuleOutcome:
        if len(rows) < 2:
            return RuleOutcome(
                "lynch_garp.rule_4_inventory_vs_sales",
                _INSUFFICIENT,
                None,
                factor,
                "needs two fiscal years",
            )
        latest, prev = rows[0], rows[1]
        inv_l = getattr(latest, "inventory", None)
        inv_p = getattr(prev, "inventory", None)
        if inv_l is None and inv_p is None:
            return RuleOutcome(
                "lynch_garp.rule_4_inventory_vs_sales",
                _WATCH,
                None,
                factor,
                "no inventory reported — typical for service/asset-light "
                "companies; inventory watch not applicable",
            )
        if (
            inv_l is None
            or inv_p is None
            or inv_l == 0
            or inv_p == 0
            or latest.revenue is None
            or prev.revenue is None
            or prev.revenue == 0
        ):
            return RuleOutcome(
                "lynch_garp.rule_4_inventory_vs_sales",
                _INSUFFICIENT,
                None,
                factor,
                "inventory or revenue data incomplete",
            )
        inv_growth = inv_l / inv_p - 1.0
        sales_growth = latest.revenue / prev.revenue - 1.0
        detail = f"inventory growth {inv_growth:.1%} vs sales growth {sales_growth:.1%}"
        if inv_growth <= sales_growth:
            return RuleOutcome(
                "lynch_garp.rule_4_inventory_vs_sales",
                _PASS,
                inv_growth,
                sales_growth,
                detail,
            )
        if inv_growth <= factor * sales_growth:
            return RuleOutcome(
                "lynch_garp.rule_4_inventory_vs_sales",
                _WATCH,
                inv_growth,
                factor * sales_growth,
                detail,
            )
        return RuleOutcome(
            "lynch_garp.rule_4_inventory_vs_sales",
            _FAIL,
            inv_growth,
            factor * sales_growth,
            detail,
        )

    def _rule_5_dividend_adjusted_peg(self, rows, price: float | None) -> RuleOutcome:
        latest = rows[0] if rows else None
        dividends = (latest.dividends_paid or 0) if latest else 0
        if dividends <= 0:
            return RuleOutcome(
                RULE_5_DIVIDEND_ADJUSTED_PEG.id,
                _INSUFFICIENT,
                None,
                _PEG_PASS,
                "company pays no dividends",
            )
        eps = self._eps(latest)
        if price is None or eps is None or eps <= 0:
            return RuleOutcome(
                RULE_5_DIVIDEND_ADJUSTED_PEG.id,
                _INSUFFICIENT,
                None,
                _PEG_PASS,
                "no price or earnings for the dividend-adjusted PEG",
            )
        growth = self._earnings_cagr(rows)
        if growth is None or growth <= 0:
            return RuleOutcome(
                RULE_5_DIVIDEND_ADJUSTED_PEG.id,
                _INSUFFICIENT,
                None,
                _PEG_PASS,
                "no earnings-growth series for the dividend-adjusted PEG",
            )
        pe = price / eps
        if not is_meaningful_pe(pe):
            return RuleOutcome(
                RULE_5_DIVIDEND_ADJUSTED_PEG.id,
                _FAIL,
                pe,
                _PEG_PASS,
                f"P/E {pe:.1f} is not meaningful (loss or extreme)",
            )
        yield_ = (dividends / latest.shares_outstanding) / price
        pegy = (pe / (growth * 100.0)) / (1.0 + yield_)
        detail = f"PEGY {pegy:.2f} (dividend yield {yield_:.2%})"
        if pegy <= _PEG_PASS:
            return RuleOutcome(
                RULE_5_DIVIDEND_ADJUSTED_PEG.id, _PASS, pegy, _PEG_PASS, detail
            )
        if pegy <= _PEG_WATCH:
            return RuleOutcome(
                RULE_5_DIVIDEND_ADJUSTED_PEG.id, _WATCH, pegy, _PEG_WATCH, detail
            )
        return RuleOutcome(
            RULE_5_DIVIDEND_ADJUSTED_PEG.id, _FAIL, pegy, _PEG_WATCH, detail
        )

    # ------------------------------------------------------------------
    # verdict, score, confidence, flags
    # ------------------------------------------------------------------
    @staticmethod
    def _verdict(category, outcomes, rows) -> tuple[Verdict, float | None, Confidence]:
        if category is LynchCategory.SLOW_GROWER:
            return LynchGARPMethodology._slow_grower_verdict(outcomes, rows)
        core_ids = {r.id for r in VERDICT_RULES}
        core = [o for o in outcomes if o.rule_id in core_ids]
        insufficient = [o for o in core if o.outcome == _INSUFFICIENT]
        if len(insufficient) > 2:
            return Verdict.INSUFFICIENT_DATA, None, Confidence.LOW
        passed = [o for o in core if o.outcome == _PASS]
        failed = [o for o in core if o.outcome == _FAIL]
        score = LynchGARPMethodology._score(outcomes)
        confidence = LynchGARPMethodology._confidence(outcomes)
        if failed:
            return Verdict.AVOID, score, confidence
        if len(passed) == 3:
            return Verdict.BUY, score, confidence
        if len(passed) == 2:
            return Verdict.WATCH, score, confidence
        if len(passed) == 1:
            return Verdict.HOLD, score, confidence
        return Verdict.AVOID, score, confidence

    @staticmethod
    def _slow_grower_verdict(
        outcomes, rows
    ) -> tuple[Verdict, float | None, Confidence]:
        """Slow growers are judged on dividend stability, not PEG.

        BUY when the dividend did not decline in >= 4 of the last 5 years and
        the net margin is stable; WATCH when the dividend was paid every year;
        HOLD otherwise. A core-rule FAIL (earnings decline, debt) caps the
        verdict at WATCH — stable dividends do not excuse a broken balance
        sheet.
        """
        score = LynchGARPMethodology._score(outcomes)
        confidence = LynchGARPMethodology._confidence(outcomes)
        if (
            LynchGARPMethodology._dividend_years(rows, _CATEGORY_YEARS)
            < _CATEGORY_YEARS
        ):
            return Verdict.HOLD, score, confidence
        core_ids = {r.id for r in VERDICT_RULES}
        core_failed = any(o.outcome == _FAIL for o in outcomes if o.rule_id in core_ids)
        grew = LynchGARPMethodology._non_declining_dividends(rows)
        margin_stable = LynchGARPMethodology._net_margin_stable(rows)
        if grew >= 4 and margin_stable and not core_failed:
            return Verdict.BUY, score, confidence
        return Verdict.WATCH, score, confidence

    @staticmethod
    def _score(outcomes) -> float | None:
        evaluable = [o for o in outcomes if o.outcome != _INSUFFICIENT]
        if len(evaluable) < 2:
            return None
        passed = sum(1 for o in evaluable if o.outcome == _PASS)
        return round(passed / len(evaluable) * 100.0, 2)

    @staticmethod
    def _confidence(outcomes) -> Confidence:
        insufficient = sum(1 for o in outcomes if o.outcome == _INSUFFICIENT)
        if insufficient == 0:
            return Confidence.HIGH
        if insufficient <= 2:
            return Confidence.MEDIUM
        return Confidence.LOW

    @staticmethod
    def _red_flags(outcomes) -> list[str]:
        flags = []
        for o in outcomes:
            if o.outcome == _FAIL:
                flags.append(f"{_FLAG_BY_RULE[o.rule_id]}: {o.detail}")
        return flags

    @staticmethod
    def _reasons(outcomes, verdict, category=None) -> list[str]:
        parts = []
        for o in outcomes:
            mark = {
                _PASS: "PASS",
                _WATCH: "WATCH",
                _FAIL: "FAIL",
                _INSUFFICIENT: "N/A",
            }[o.outcome]
            parts.append(f"[{mark}] {o.detail}")
        if category is LynchCategory.CYCLICAL:
            parts.append("cyclical: check position in the cycle")
        parts.append(f"verdict: {verdict.value}")
        return parts

    @staticmethod
    def _metrics(
        outcomes,
        price: float | None,
        rows,
        category: LynchCategory | None = None,
        criterion: str | None = None,
    ) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            o.rule_id.replace("lynch_garp.", ""): o.value for o in outcomes
        }
        metrics["rule_outcomes"] = {o.rule_id: o.outcome for o in outcomes}
        metrics["current_price"] = price
        metrics["fiscal_years_analyzed"] = len(rows)
        if category is not None:
            metrics["lynch_category"] = category.value
            metrics["lynch_category_label"] = CATEGORY_LABELS[category]
            metrics["rule_1_criterion"] = criterion
        if category in _SCORELESS_CATEGORIES:
            metrics["score_note"] = _SCORE_NOTES[category]
        return metrics
