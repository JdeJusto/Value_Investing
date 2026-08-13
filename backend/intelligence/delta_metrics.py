"""Fundamental deltas: how metrics are *changing*, not just their levels.

Compares the latest year against the previous one (and the change of
the change, i.e. acceleration). Deltas are expressed as raw fractions
(0.02 = +2 percentage points) and are the input to momentum scoring,
inflection detection and signal triggers. Depends only on normalized
financials.
"""

from typing import Optional

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.intelligence.quality_metrics import (
    equity_of,
    gross_margin,
    ordered_asc,
    roic,
)


def _growth(prev: Optional[float], last: Optional[float]) -> Optional[float]:
    if prev is None or last is None or prev == 0:
        return None
    return (last - prev) / abs(prev)


def _margin_delta(rows: list[NormalizedFinancials], margin_fn) -> Optional[float]:
    if len(rows) < 2:
        return None
    ordered = ordered_asc(rows)
    return (
        (margin_fn(ordered[-1]) or 0.0) - (margin_fn(ordered[-2]) or 0.0)
        if margin_fn(ordered[-1]) is not None and margin_fn(ordered[-2]) is not None
        else None
    )


def _net_margin(row: NormalizedFinancials) -> Optional[float]:
    if row.revenue is not None and row.net_income is not None and row.revenue != 0:
        return row.net_income / row.revenue
    return None


def _operating_margin(row: NormalizedFinancials) -> Optional[float]:
    if (
        row.revenue is not None
        and row.operating_income is not None
        and row.revenue != 0
    ):
        return row.operating_income / row.revenue
    return None


def _debt_equity(row: NormalizedFinancials) -> Optional[float]:
    eq = equity_of(row)
    if row.total_debt is None or not eq:
        return None
    return row.total_debt / eq


def compute_delta_metrics(rows: list[NormalizedFinancials]) -> dict:
    """Year-over-year changes and accelerations for the latest period.

    Returns ``None`` for every delta when there is not enough history.
    ``*_growth_delta`` fields are accelerations (growth of growth);
    ``*_delta`` fields are simple year-over-year changes.
    """
    ordered = ordered_asc(rows)
    if len(ordered) < 2:
        return {
            "revenue_growth_last": None,
            "revenue_growth_prev": None,
            "revenue_growth_delta": None,
            "gross_margin_delta": None,
            "net_margin_delta": None,
            "operating_margin_delta": None,
            "roic_delta": None,
            "fcf_delta": None,
            "debt_delta": None,
            "net_income_change": None,
        }

    last_two = ordered[-2:]

    def revenue_growth(pair: list[NormalizedFinancials]) -> Optional[float]:
        if len(pair) < 2:
            return None
        return _growth(pair[0].revenue, pair[1].revenue)

    rev_growth_last = revenue_growth(ordered[-2:])
    rev_growth_prev = revenue_growth(ordered[-3:-1]) if len(ordered) >= 3 else None

    fcf_prev = last_two[0].free_cash_flow
    fcf_last = last_two[1].free_cash_flow
    fcf_delta = _growth(fcf_prev, fcf_last)

    fcf_growth_last = fcf_delta
    fcf_growth_prev = None
    if len(ordered) >= 3:
        fcf_prev_prev = ordered[-3].free_cash_flow
        fcf_growth_prev = _growth(fcf_prev_prev, fcf_prev)
    fcf_growth_delta = (
        fcf_growth_last - fcf_growth_prev
        if fcf_growth_last is not None and fcf_growth_prev is not None
        else None
    )

    roic_prev = roic(ordered[-2])
    roic_last = roic(ordered[-1])
    roic_delta = (
        roic_last - roic_prev
        if roic_prev is not None and roic_last is not None
        else None
    )

    de_prev = _debt_equity(ordered[-2])
    de_last = _debt_equity(ordered[-1])
    debt_delta = (
        de_last - de_prev if de_prev is not None and de_last is not None else None
    )

    prev_income = ordered[-2].net_income
    net_income_change = _growth(prev_income, last_two[1].net_income)

    return {
        "revenue_growth_last": rev_growth_last,
        "revenue_growth_prev": rev_growth_prev,
        "revenue_growth_delta": (
            rev_growth_last - rev_growth_prev
            if rev_growth_last is not None and rev_growth_prev is not None
            else None
        ),
        "gross_margin_delta": _margin_delta(ordered, gross_margin),
        "net_margin_delta": _margin_delta(ordered, _net_margin),
        "operating_margin_delta": _margin_delta(ordered, _operating_margin),
        "roic_delta": roic_delta,
        "fcf_delta": fcf_delta,
        "fcf_growth_last": fcf_growth_last,
        "fcf_growth_prev": fcf_growth_prev,
        "fcf_growth_delta": fcf_growth_delta,
        "debt_delta": debt_delta,
        "net_income_change": net_income_change,
    }
