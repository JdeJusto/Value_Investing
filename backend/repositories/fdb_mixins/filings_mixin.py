"""Filings listing and the fundamentals freshness fingerprint.

Mixin for :class:`FinancialDatabaseRepository` (pure move).
"""

from __future__ import annotations

import hashlib
from datetime import date


class FilingsMixin:
    def fundamentals_fingerprint(self, ticker: str) -> str | None:
        """Cheap change-detector digest of a company's stored fundamentals.

        One round trip on cheap, well-indexed rows: the company row itself
        (``updated_at`` is touched by every ingestion, ``last_synced_at`` by
        every targeted SEC sync) plus the company's filing count and newest
        filing date. Any new filing or re-sync changes the digest, which is
        what invalidates the analysis cache (backend/services/analysis_cache.py).

        Deliberately NOT derived from ``financial_facts``: aggregating that
        table per company costs as much as reading the history it is meant to
        replace (~130 ms measured after the 2026-09-27 sweep bloated the
        indexes), which would cancel the whole point of the cache. The
        accepted trade-off: a restatement that adds facts without any new
        filing and without touching the company row keeps the digest — the
        next sync of that company bumps ``updated_at`` and invalidates it.

        Returns None when the ticker is unknown, the repository is
        unavailable or the company has no filings — i.e. "cannot cache",
        never "cache is fresh".
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.updated_at AS company_updated,
                           c.last_synced_at AS company_synced,
                           (SELECT count(*) FROM filings f
                             WHERE f.company_id = c.id) AS filing_count,
                           (SELECT max(f.created_at) FROM filings f
                             WHERE f.company_id = c.id) AS last_filing
                    FROM companies c
                    JOIN company_identifiers ci ON ci.company_id = c.id
                    WHERE ci.identifier_type = 'TICKER'
                      AND ci.identifier_value = %s
                    LIMIT 1
                    """,
                    (str(ticker).upper(),),
                )
                row = cur.fetchone()
        except Exception:  # noqa: BLE001 — a fingerprint failure is a cache miss
            return None
        if not row or int(row.get("filing_count") or 0) == 0:
            return None
        raw = "|".join(
            str(row.get(key) or "")
            for key in (
                "company_updated",
                "company_synced",
                "filing_count",
                "last_filing",
            )
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def list_filings(
        self,
        ticker: str,
        form_types: list[str] | None = None,
        fiscal_years: list[int] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Official filings for a ticker, newest first, filtered in SQL.

        The submissions importer leaves ``filings.fiscal_year`` NULL and
        ``fiscal_period`` at 'FY' for every row, so ``fiscal_years`` filters
        on the year derived from ``period_end`` (falling back to
        ``filing_date``). ``filing_url`` is the primary-document URL when the
        importer stored it (0.3% of rows); callers fall back to the index URL.
        """
        company_id = self._get_company_id_by_ticker(ticker)
        if not company_id:
            return []

        sql = """
            SELECT
                f.accession_number,
                f.form,
                f.filing_date,
                f.period_end,
                f.fiscal_year,
                f.fiscal_period,
                f.is_amended,
                f.filing_url,
                ci.identifier_value AS cik
            FROM filings f
            JOIN company_identifiers ci
              ON ci.company_id = f.company_id
             AND ci.identifier_type = 'CIK'
            WHERE f.company_id = %s
        """
        params: list = [company_id]
        if form_types:
            sql += " AND f.form = ANY(%s)"
            params.append([form.upper() for form in form_types])
        if fiscal_years:
            sql += (
                " AND EXTRACT(YEAR FROM COALESCE(f.period_end, f.filing_date))"
                " = ANY(%s)"
            )
            params.append([int(year) for year in fiscal_years])
        if start_date is not None:
            sql += " AND f.filing_date >= %s"
            params.append(start_date)
        if end_date is not None:
            sql += " AND f.filing_date <= %s"
            params.append(end_date)
        sql += " ORDER BY f.filing_date DESC, f.form ASC"
        if limit is not None:
            sql += " LIMIT %s"
            params.append(int(limit))

        with self._get_connection().cursor() as cur:
            cur.execute(sql, tuple(params))
            return [dict(row) for row in cur.fetchall()]
