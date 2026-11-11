"""Greenblatt Magic Formula overlay checks.

The ranking file stays the primary input: the methodology still looks up the
pre-computed ROC / earnings-yield rank and never recomputes the cross-sectional
ranking. This module adds a weighted overlay around that rank so the verdict
is a transparent pass ratio instead of a single percentile cut:

- **ranking**: the ticker is in the file, combined rank in the top 50 / top 100;
- **ROC decomposition**: positive EBIT, ROC >= 20%, capital turnover computable;
- **earnings-yield decomposition**: EY >= 8%, EY >= 12%, enterprise value
  positive;
- **quality overlay**: market cap > $100M, revenue positive, the financial-
  company scope guard.

The book, *The Little Book That Beats the Market* (2005), was **not available**
when this module was written (see
``docs/books_notes/the-little-book-that-beats-the-market.md``). Every source
therefore says ``page="public knowledge"`` and the threshold is labelled an
approximation, not a page citation. The ranking thresholds (top 50 / top 100)
and the ROC/EY bars are public-knowledge paraphrases of the Magic Formula.
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import SourceRef
from backend.methodologies.common.weighted import WeightedCheck, WeightedResult
from backend.methodologies.common.weighted import result as _result

_BOOK = "The Little Book That Beats the Market"
_EDITION = "1st edition"
_YEAR = 2005
_ERA = "2005"
_CAUTION = (
    "approximation — the book was not available; this is a public-knowledge "
    "threshold, not a cited page"
)

#: Market-cap floor for the quality overlay ($100M).
MIN_MARKET_CAP = 100_000_000.0


def _public(note: str) -> SourceRef:
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page="public knowledge",
        era=_ERA,
        us_caution=f"{_CAUTION}: {note}",
    )


#: Rule categories used by the CLI groups and docs.
CATEGORIES = (
    "ranking",
    "return_on_capital",
    "earnings_yield",
    "quality",
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _row_for(
    rows: list[NormalizedFinancials], entry: dict | None
) -> NormalizedFinancials | None:
    """The fundamentals row the ranking refers to (latest as fallback)."""
    fiscal_year = (entry or {}).get("fiscal_year")
    if fiscal_year is not None:
        for row in rows:
            if row.fiscal_year == fiscal_year:
                return row
    return rows[0] if rows else None


def _debt(row: NormalizedFinancials | None) -> float:
    return float(row.total_debt or 0.0) if row is not None else 0.0


def _cash(row: NormalizedFinancials | None) -> float:
    return float(row.cash_and_equivalents or 0.0) if row is not None else 0.0


def _ebit(row: NormalizedFinancials | None) -> float | None:
    if row is None or row.ebit is None:
        return None
    return float(row.ebit)


def _market_cap(row: NormalizedFinancials | None, entry: dict | None) -> float | None:
    """Market cap from the ranking entry, else derived from EBIT / EY.

    The ranking script does not store market cap, but it stores the earnings
    yield that was computed from it: ``EV = EBIT / EY`` and therefore
    ``market cap = EV - debt + cash``. This keeps the methodology hermetic (no
    price service call) at the cost of a derivation that inherits the ranking
    row's rounding. A future ranking payload that carries ``market_cap`` is
    used directly.
    """
    entry = entry or {}
    stored = entry.get("market_cap")
    if stored is not None:
        try:
            value = float(stored)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None
    ebit = _ebit(row)
    earnings_yield = entry.get("earnings_yield")
    if ebit is None or ebit <= 0 or earnings_yield in (None, 0):
        return None
    try:
        enterprise_value = ebit / float(earnings_yield)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    value = enterprise_value - _debt(row) + _cash(row)
    return value if value > 0 else None


def _combined_rank(entry: dict | None) -> float | None:
    value = (entry or {}).get("combined_rank")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# ranking
# ---------------------------------------------------------------------------
def _rank_in_file(rows, entry) -> WeightedResult:
    check = CHECKS_BY_ID["greenblatt.rank_in_file"]
    if entry is None:
        return _result(check, None, "no ranking entry")
    combined = _combined_rank(entry)
    detail = "in the ranking file"
    if combined is not None:
        detail += f" (combined rank {combined:g})"
    return _result(check, True, detail, value=combined)


def _rank_top_50(rows, entry) -> WeightedResult:
    check = CHECKS_BY_ID["greenblatt.rank_top_50"]
    combined = _combined_rank(entry)
    if combined is None:
        return _result(check, None, "combined rank missing")
    return _result(
        check,
        combined <= 50,
        f"combined rank {combined:g} vs <= 50",
        value=combined,
        threshold=50.0,
    )


def _rank_top_100(rows, entry) -> WeightedResult:
    check = CHECKS_BY_ID["greenblatt.rank_top_100"]
    combined = _combined_rank(entry)
    if combined is None:
        return _result(check, None, "combined rank missing")
    return _result(
        check,
        combined <= 100,
        f"combined rank {combined:g} vs <= 100",
        value=combined,
        threshold=100.0,
    )


# ---------------------------------------------------------------------------
# ROC decomposition
# ---------------------------------------------------------------------------
def _ebit_positive(rows, entry) -> WeightedResult:
    check = CHECKS_BY_ID["greenblatt.roc_ebit_positive"]
    row = _row_for(rows, entry)
    ebit = _ebit(row)
    if ebit is None:
        return _result(check, None, "EBIT missing")
    return _result(
        check,
        ebit > 0,
        f"EBIT ${ebit:,.0f}",
        value=ebit,
        threshold=0.0,
    )


def _roc_above_20(rows, entry) -> WeightedResult:
    check = CHECKS_BY_ID["greenblatt.roc_above_20"]
    roc = (entry or {}).get("roc")
    if roc is None:
        return _result(check, None, "ROC missing from the ranking")
    value = float(roc)
    return _result(
        check,
        value >= 0.20,
        f"ROC {value:.1%} vs >= 20%",
        value=value,
        threshold=0.20,
    )


def _capital_turnover_computable(rows, entry) -> WeightedResult:
    """Capital turnover = revenue / (net working capital + net PPE)."""
    check = CHECKS_BY_ID["greenblatt.roc_capital_turnover_computable"]
    row = _row_for(rows, entry)
    if row is None:
        return _result(check, None, "no fundamentals")
    if (
        row.revenue is None
        or row.current_assets is None
        or row.current_liabilities is None
        or row.net_ppe is None
    ):
        return _result(check, None, "revenue, working capital or net PPE missing")
    capital = max(
        float(row.current_assets) - float(row.current_liabilities), 0.0
    ) + float(row.net_ppe)
    if capital <= 0:
        return _result(check, None, "non-positive capital employed")
    turnover = float(row.revenue) / capital
    return _result(
        check,
        turnover > 0,
        f"capital turnover {turnover:.2f}x (informational)",
        value=turnover,
        threshold=0.0,
    )


# ---------------------------------------------------------------------------
# earnings-yield decomposition
# ---------------------------------------------------------------------------
def _ey_above_8(rows, entry) -> WeightedResult:
    check = CHECKS_BY_ID["greenblatt.ey_above_8"]
    ey = (entry or {}).get("earnings_yield")
    if ey is None:
        return _result(check, None, "earnings yield missing from the ranking")
    value = float(ey)
    return _result(
        check,
        value >= 0.08,
        f"earnings yield {value:.1%} vs >= 8%",
        value=value,
        threshold=0.08,
    )


def _ey_above_12(rows, entry) -> WeightedResult:
    check = CHECKS_BY_ID["greenblatt.ey_above_12"]
    ey = (entry or {}).get("earnings_yield")
    if ey is None:
        return _result(check, None, "earnings yield missing from the ranking")
    value = float(ey)
    return _result(
        check,
        value >= 0.12,
        f"earnings yield {value:.1%} vs >= 12%",
        value=value,
        threshold=0.12,
    )


def _ev_positive(rows, entry) -> WeightedResult:
    check = CHECKS_BY_ID["greenblatt.ey_ev_positive"]
    row = _row_for(rows, entry)
    ebit = _ebit(row)
    ey = (entry or {}).get("earnings_yield")
    ev: float | None = None
    if ebit is not None and ey not in (None, 0):
        try:
            ev = ebit / float(ey)
        except (TypeError, ValueError, ZeroDivisionError):
            ev = None
    if ev is None:
        market_cap = _market_cap(row, entry)
        if market_cap is not None:
            ev = market_cap + _debt(row) - _cash(row)
    if ev is None:
        return _result(check, None, "enterprise value not computable")
    return _result(
        check,
        ev > 0,
        f"enterprise value ${ev:,.0f}",
        value=ev,
        threshold=0.0,
    )


# ---------------------------------------------------------------------------
# quality overlay
# ---------------------------------------------------------------------------
def _market_cap_above_100m(rows, entry) -> WeightedResult:
    check = CHECKS_BY_ID["greenblatt.quality_market_cap_above_100m"]
    row = _row_for(rows, entry)
    market_cap = _market_cap(row, entry)
    if market_cap is None:
        return _result(check, None, "market cap not available")
    return _result(
        check,
        market_cap >= MIN_MARKET_CAP,
        f"market cap ${market_cap:,.0f} vs >= ${MIN_MARKET_CAP:,.0f}",
        value=market_cap,
        threshold=MIN_MARKET_CAP,
    )


def _revenue_positive(rows, entry) -> WeightedResult:
    check = CHECKS_BY_ID["greenblatt.quality_revenue_positive"]
    row = _row_for(rows, entry)
    if row is None or row.revenue is None:
        return _result(check, None, "revenue missing")
    return _result(
        check,
        row.revenue > 0,
        f"revenue ${row.revenue:,.0f}",
        value=float(row.revenue),
        threshold=0.0,
    )


def _not_a_bank(rows, entry) -> WeightedResult:
    check = CHECKS_BY_ID["greenblatt.quality_not_a_bank"]
    return _result(
        check,
        None,
        (
            "informational scope guard: financials abstain before the overlay, "
            "so this rule is N/A by design"
        ),
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
CHECKS: tuple[WeightedCheck, ...] = (
    WeightedCheck(
        "greenblatt.rank_in_file",
        "In the ranking file",
        "ranking",
        2,
        "The ticker has an entry in the newest Magic Formula ranking.",
        _public("presence in the weekly ranking file"),
        _rank_in_file,
    ),
    WeightedCheck(
        "greenblatt.rank_top_50",
        "Combined rank in the top 50",
        "ranking",
        2,
        "combined_rank = rank_ROC + rank_EY <= 50.",
        _public("top-50 combined rank"),
        _rank_top_50,
    ),
    WeightedCheck(
        "greenblatt.rank_top_100",
        "Combined rank in the top 100",
        "ranking",
        2,
        "combined_rank = rank_ROC + rank_EY <= 100.",
        _public("top-100 combined rank"),
        _rank_top_100,
    ),
    WeightedCheck(
        "greenblatt.roc_ebit_positive",
        "EBIT positive",
        "return_on_capital",
        1,
        "The ROC numerator (EBIT) must be positive.",
        _public("ROC = EBIT / (net working capital + net PPE)"),
        _ebit_positive,
    ),
    WeightedCheck(
        "greenblatt.roc_above_20",
        "ROC >= 20%",
        "return_on_capital",
        1,
        "Return on capital of at least 20%.",
        _public("high-ROC quality bar"),
        _roc_above_20,
    ),
    WeightedCheck(
        "greenblatt.roc_capital_turnover_computable",
        "Capital turnover computable",
        "return_on_capital",
        0,
        "Informational: revenue / (net working capital + net PPE) is computable.",
        _public("ROC denominator decomposition"),
        _capital_turnover_computable,
    ),
    WeightedCheck(
        "greenblatt.ey_above_8",
        "Earnings yield >= 8%",
        "earnings_yield",
        1,
        "EBIT / enterprise value of at least 8%.",
        _public("cheapness bar"),
        _ey_above_8,
    ),
    WeightedCheck(
        "greenblatt.ey_above_12",
        "Earnings yield >= 12%",
        "earnings_yield",
        1,
        "EBIT / enterprise value of at least 12%.",
        _public("deep-cheapness bar"),
        _ey_above_12,
    ),
    WeightedCheck(
        "greenblatt.ey_ev_positive",
        "Enterprise value positive",
        "earnings_yield",
        1,
        "Enterprise value (market cap + debt - cash) must be positive.",
        _public("EY = EBIT / enterprise value"),
        _ev_positive,
    ),
    WeightedCheck(
        "greenblatt.quality_market_cap_above_100m",
        "Market cap > $100M",
        "quality",
        1,
        "The company is large enough for the ranking to be meaningful.",
        _public("size floor"),
        _market_cap_above_100m,
    ),
    WeightedCheck(
        "greenblatt.quality_revenue_positive",
        "Revenue positive",
        "quality",
        1,
        "Revenue must be positive for a meaningful ROC denominator.",
        _public("operating quality floor"),
        _revenue_positive,
    ),
    WeightedCheck(
        "greenblatt.quality_not_a_bank",
        "Not a bank (scope guard)",
        "quality",
        0,
        "Informational: financial companies abstain before the overlay runs.",
        _public("the ROC denominator assumes an industrial balance sheet"),
        _not_a_bank,
    ),
)

CHECKS_BY_ID: dict[str, WeightedCheck] = {check.rule_id: check for check in CHECKS}


def run_checks(
    rows: list[NormalizedFinancials], entry: dict | None
) -> list[WeightedResult]:
    """Evaluate every overlay check against one ranking entry."""
    return [check.evaluate(rows, entry) for check in CHECKS]


__all__ = [
    "CATEGORIES",
    "CHECKS",
    "CHECKS_BY_ID",
    "MIN_MARKET_CAP",
    "run_checks",
]
