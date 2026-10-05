"""Fiscal year end dates and the latest completed year.

Mixin for :class:`FinancialDatabaseRepository` (pure move).
"""

from __future__ import annotations

from datetime import date

from backend.repositories.fdb_concept_mapping import (
    CORE_STATEMENT_CONCEPTS,
)


class FiscalYearMixin:
    def get_fiscal_year_end_date(self, ticker: str, fiscal_year: int) -> date | None:
        """Cached fiscal year end: per-year DB lookup, content-addressed.

        The date is derived from the company's facts and only moves when they
        change, so it is cached next to the shares outstanding under the same
        fingerprint. Stored as an ISO string and rebuilt into a ``date`` here.
        """
        cache = self._lookup_cache()
        if cache is None:
            return self._get_fiscal_year_end_date_uncached(ticker, fiscal_year)
        fingerprint = cache.fingerprint_for(ticker)
        if fingerprint is None:
            return self._get_fiscal_year_end_date_uncached(ticker, fiscal_year)
        from backend.services.analysis_cache import SECTION_FISCAL_YEAR_END

        key = str(int(fiscal_year))
        if cache._entry_present(ticker, fingerprint, SECTION_FISCAL_YEAR_END, key):
            value = cache.get_lookup(ticker, fingerprint, SECTION_FISCAL_YEAR_END, key)
            if value is None:
                return None
            try:
                return date.fromisoformat(str(value))
            except ValueError:
                return None
        value = self._get_fiscal_year_end_date_uncached(ticker, fiscal_year)
        cache.put_lookup(
            ticker,
            fingerprint,
            SECTION_FISCAL_YEAR_END,
            key,
            value.isoformat() if value is not None else None,
        )
        return value

    def _get_fiscal_year_end_date_uncached(
        self, ticker: str, fiscal_year: int
    ) -> date | None:
        """Return the best-known fiscal year end date for a ticker/year.

        The value is the ``period_end`` of the core 'FY' statement fact that
        most plausibly describes the bucket's own fiscal year.  Only the core
        concepts are considered because one-off disclosures tagged 'FY' (fee
        schedules, Entity% cover-page facts) can carry a later period_end that
        is not the fiscal year end.

        Three rules, in priority order:

        1. *Calendar-year match wins.* The bucket label is the calendar year of
           the fiscal year end (Apple FY2025 ends 2025-09-27, Salesforce FY2025
           ends 2025-01-31), so facts whose ``period_end`` falls *outside* that
           calendar year are comparatives or cross-year leaks from a 10-K that
           a sync tagged under several fiscal years at once.  AAPL's FY2025
           bucket, for example, holds its FY2023 comparatives (period_end
           2023-09-30) whose *longer* annual span (370 days vs 363) used to
           hijack the span-first ordering and return the wrong year end for
           every recent year.
        2. *Annual span over quarterly rows.* The quarterly rows of a 10-K
           supplemental quarterly table are retagged 'FY' by SEC, and for a
           Jan-31 fiscal-year-end company they land in the PREVIOUS bucket with
           a LATER calendar period_end (e.g. Salesforce FY2013 bucket holds
           Q1-Q3 FY2014 quarters ending Apr/Jul/Oct 2013, all inside calendar
           2013).  Among calendar-year-matched facts the longest span wins, so
           the ~91-273 day quarters lose to the ~365 day annual.
        3. *Latest period_end breaks ties* among equally plausible annual facts.

        Args:
            ticker: Company ticker symbol
            fiscal_year: Fiscal year

        Returns:
            Fiscal year end date if found, None otherwise
        """
        try:
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return None

            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT f.period_end::date AS period_end
                    FROM financial_facts f
                    WHERE f.company_id = %s
                      AND f.fiscal_year = %s
                      AND UPPER(f.fiscal_period) = 'FY'
                      AND f.period_end IS NOT NULL
                      AND f.concept = ANY(%s::text[])
                    ORDER BY (EXTRACT(YEAR FROM f.period_end) = %s) DESC,
                             (f.period_end - COALESCE(f.period_start, f.period_end)) DESC,
                             f.period_end DESC
                    LIMIT 1
                """,
                    (company_id, fiscal_year, CORE_STATEMENT_CONCEPTS, fiscal_year),
                )

                result = cur.fetchone()
                if result and result["period_end"] is not None:
                    period_end = result["period_end"]
                    if isinstance(period_end, date):
                        return period_end
                    return date.fromisoformat(str(period_end)[:10])
                return None

        except Exception:  # noqa: BLE001 — a DB failure reads as "unknown"
            return None

    def get_latest_completed_fiscal_year(self, ticker: str) -> int | None:
        """Return the most recent fiscal year that has annual ('FY') facts.

        ``list_years`` returns every year with any facts, including the current
        in-progress year (partial quarterly data). Completed-year comparisons
        should anchor on the latest year that has a full annual report.

        Args:
            ticker: Company ticker symbol

        Returns:
            Completed fiscal year if found, None otherwise
        """
        try:
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return None

            conn = self._get_connection()
            with conn.cursor() as cur:
                # A 'FY' period is only meaningful when it comes from an actual
                # annual report. Shelf/registration filings (424B5, S-3ASR...)
                # also carry fiscal_period='FY' for their filing-fee facts, so
                # they are excluded to avoid treating the in-progress year as
                # completed. A stray (mis-filed) annual bucket whose embedded
                # facts describe an older period, e.g. a 10-K labelled fut+1
                # but only carrying prior comparatives, is rejected by picking
                # the bucket with the most recent true fiscal-year-end rather
                # than simply the largest fiscal_year number.
                cur.execute(
                    """
                    SELECT f.fiscal_year
                    FROM financial_facts f
                    WHERE f.company_id = %s
                      AND UPPER(f.fiscal_period) = 'FY'
                      AND UPPER(f.form) IN ('10-K', '10-K/A', '20-F', '20-F/A')
                      AND f.fiscal_year IS NOT NULL
                      AND f.period_end IS NOT NULL
                      AND f.concept NOT LIKE 'Entity%%'
                    GROUP BY f.fiscal_year
                    ORDER BY MAX(f.period_end) DESC
                    LIMIT 1
                """,
                    (company_id,),
                )

                result = cur.fetchone()
                if result and result["fiscal_year"] is not None:
                    return int(result["fiscal_year"])
                return None

        except Exception:  # noqa: BLE001 — a DB failure reads as "unknown"
            return None
