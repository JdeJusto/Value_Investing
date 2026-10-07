"""Pure helpers shared by the Financial-DataBase repository mixins.

Pure move out of ``financial_database_repository`` (which re-exports
``_as_date``/``_cumulative_split_multiplier`` for the tests).
"""

from __future__ import annotations

from datetime import date


def _period_end_year(value) -> int | None:
    """Calendar year of a ``period_end`` value, or None when unknown.

    Used by ``_normalize_financial_facts`` to keep each fiscal-year bucket
    scoped to the rows belonging to its own labelled year.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value.year
    try:
        return date.fromisoformat(str(value)[:10]).year
    except (ValueError, TypeError):
        return None


def _as_date(value) -> date | None:
    """Normalize a ``date`` or ISO string to a :class:`date`, or None."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def select_split_events(rows: list) -> list[tuple]:
    """Pick the split *effective dates* out of raw ratio facts.

    Each entry in ``rows`` is a ``(period_start, period_end, ratio)`` triple
    from the XBRL ``StockholdersEquityNoteStockSplitConversionRatio*`` facts.

    An **instant** fact (``period_start`` is None) carries the split's
    effective date as its ``period_end``. A *duration* fact repeats the same
    split across a reporting period, so its ``period_end`` is a quarter/year
    end rather than the split date. Counting both counts one split several
    times and lets a re-disclosure filed years later land *after* a fiscal
    year that in fact already reflects the split (CoStar's 10:1 split of
    2021-06-07 is re-disclosed as a duration fact ending 2025-06-30, which
    used to give every pre-mid-2025 year an extra 10x).

    When a company discloses any instant fact, those period_ends are the
    effective dates, so only they are returned. A company that only ever
    reports duration facts keeps them (deduped by the caller); a company with
    no facts returns an empty list and the factor stays 1.0.
    """
    instants = [
        (period_end, ratio)
        for period_start, period_end, ratio in (rows or [])
        if period_start is None
    ]
    if instants:
        return instants
    return [(period_end, ratio) for _start, period_end, ratio in (rows or [])]


def _cumulative_split_multiplier(fy_end, split_rows: list) -> float:
    """Product of DISTINCT split ratios effective strictly after ``fy_end``.

    ``fy_end`` is a row's fiscal year end (date or ISO string). Each entry in
    ``split_rows`` is an ``(period_end, ratio)`` pair from the XBRL
    ``StockholdersEquityNoteStockSplitConversionRatio*`` facts (period_end =
    effective split date, ratio = shares-after / shares-before). A 4:1 split
    effective after the row's year means each as-reported share has since
    become 4 shares, so the past count multiplies by 4 to sit on today's
    basis. Duplicates of the same split event (the note is re-filed across
    10-Ks) are counted once. Returns 1.0 when nothing applies.

    Pure function — no database, no network — so the split adjustment can be
    unit-tested and reasoned about without infrastructure.
    """
    end = _as_date(fy_end)
    if end is None:
        return 1.0
    multiplier = 1.0
    seen: set = set()
    for period_end, ratio in split_rows or []:
        effective = _as_date(period_end)
        if effective is None or ratio is None:
            continue
        try:
            ratio_f = float(ratio)
        except (TypeError, ValueError):
            continue
        if effective <= end or ratio_f <= 0:
            continue
        key = (effective, ratio_f)
        if key in seen:
            continue
        seen.add(key)
        multiplier *= ratio_f
    return multiplier
