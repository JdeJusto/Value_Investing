"""Point-in-time reads: fundamentals known on a date + historical universe.

A PIT read filters on ``financial_facts.filing_date <= as_of`` (the date the
fact became public) and ``period_end <= as_of`` (the period had actually
ended). Restatements coexist as separate rows, so versions are collapsed per
(concept, period) keeping the latest filing known at ``as_of``; a restatement
filed later is invisible.

Requires Financial-DataBase 0.4.0 (``idx_financial_facts_pit`` and the
``sp500_constituents`` table). Every method degrades to an empty result when
the schema or the connection is unavailable.
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.repositories.fdb_mixins.helpers import (
    _as_date,
    _cumulative_split_multiplier,
)

logger = logging.getLogger(__name__)

#: Columns read from financial_facts for a PIT history.
_PIT_COLUMNS = """
    f.concept,
    f.value,
    f.unit,
    f.fiscal_year,
    f.fiscal_period,
    f.period_end,
    f.period_start,
    f.filing_date
"""


class PitMixin:
    """Point-in-time fundamentals and S&P 500 membership."""

    # ------------------------------------------------------------------
    # Fundamentals as known on a date
    # ------------------------------------------------------------------
    def list_years_pit(
        self,
        ticker: str,
        as_of: date,
        max_years: int | None = None,
    ) -> list[NormalizedFinancials]:
        """Annual history as it was known on ``as_of`` (most recent first).

        Only ``FY`` facts filed on or before ``as_of`` are read. Within each
        (concept, period) the latest filing known at ``as_of`` wins, which
        keeps the value that was public then and drops later restatements.
        """
        company_id = self._get_company_id_by_ticker(ticker)
        if not company_id:
            return []
        return self.list_years_pit_by_company_id(
            company_id,
            as_of,
            ticker=ticker.upper(),
            max_years=max_years,
        )

    def list_years_pit_by_company_id(
        self,
        company_id: str,
        as_of: date,
        *,
        ticker: str | None = None,
        max_years: int | None = None,
    ) -> list[NormalizedFinancials]:
        """Company-id variant of :meth:`list_years_pit`."""
        as_of = _as_date(as_of) or as_of
        try:
            company_sector = self._get_company_sector(ticker) if ticker else None
            company_industry = self._get_company_industry(ticker) if ticker else None

            sql = f"""
                SELECT {_PIT_COLUMNS}
                FROM financial_facts f
                WHERE f.company_id = %s
                  AND UPPER(f.fiscal_period) = 'FY'
                  AND f.filing_date <= %s
                  AND f.period_end <= %s
            """
            params: list = [company_id, as_of, as_of]
            if max_years is not None:
                # Push the window into SQL; one extra year absorbs fiscal-year
                # labels whose period_end falls in the previous calendar year.
                sql += " AND f.fiscal_year >= %s"
                params.append(int(as_of.year) - int(max_years))
            sql += " ORDER BY f.fiscal_year DESC"

            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                facts = cur.fetchall()
            if not facts:
                return []

            # Collapse restatement versions: keep the latest filing per
            # (fiscal_year, concept, period_start, period_end) known at as_of.
            best: dict[tuple, dict] = {}
            for row in facts:
                key = (
                    row["fiscal_year"],
                    row["concept"],
                    row["period_start"],
                    row["period_end"],
                )
                previous = best.get(key)
                if previous is None or (row.get("filing_date") or date.min) > (
                    previous.get("filing_date") or date.min
                ):
                    best[key] = row

            by_year: dict[int, list] = {}
            for row in best.values():
                by_year.setdefault(int(row["fiscal_year"]), []).append(row)

            split_rows = self._fetch_split_ratio_facts(company_id)

            results: list[NormalizedFinancials] = []
            for year in sorted(by_year, reverse=True):
                try:
                    fy_end = max(
                        (
                            pe
                            for pe in (
                                _as_date(r.get("period_end")) for r in by_year[year]
                            )
                            if pe
                        ),
                        default=None,
                    )
                    split_factor = _cumulative_split_multiplier(fy_end, split_rows)
                    statements = self._normalize_financial_facts(
                        by_year[year], bucket_year=year
                    )
                    statements = self._calculate_derived_fields(statements)
                    financials = self._build_normalized_financials(
                        ticker=(ticker or "").upper(),
                        fiscal_year=year,
                        statements=statements,
                        split_adjustment_factor=split_factor,
                        sector=company_sector,
                        industry=company_industry,
                    )
                    if financials is not None:
                        results.append(financials)
                except Exception:  # noqa: BLE001, S112 — one bad year must not drop the rest
                    continue
            return results
        except Exception:  # a broken PIT read degrades to empty
            logger.debug("point-in-time read failed", exc_info=True)
            return []

    def get_core_financials_pit(
        self,
        company_id: str,
        fiscal_year: int,
        as_of_date: date,
    ) -> dict | None:
        """Eight canonical fields for one year as known on ``as_of_date``.

        ``company_id`` may be a UUID (the FDB key) or a ticker. Returns the
        same keys as :meth:`get_core_financials` (USD-converted core fields
        plus ``liabilities_effective``) for callers that need the flat shape.
        """
        company = str(company_id)
        ticker = None
        try:
            UUID(company)
        except (ValueError, AttributeError):
            # Not a UUID: the caller already passed a ticker.
            ticker = company.upper()
        if ticker is None:
            try:
                with self._get_connection().cursor() as cur:
                    cur.execute(
                        "SELECT ticker FROM company_listings WHERE company_id = %s "
                        "AND is_active ORDER BY is_primary DESC, listing_date DESC "
                        "NULLS LAST LIMIT 1",
                        (company,),
                    )
                    row = cur.fetchone()
                if row and row.get("ticker"):
                    ticker = str(row["ticker"]).upper()
            except Exception:  # noqa: BLE001 — UUID lookup is optional
                ticker = company
        history = self.list_years_pit(ticker, as_of_date)
        row = next(
            (item for item in history if item.fiscal_year == int(fiscal_year)),
            None,
        )
        if row is None:
            return None
        return {
            "ticker": ticker,
            "fiscal_year": row.fiscal_year,
            "period_end": self.get_fiscal_year_end_date(ticker, int(fiscal_year)),
            "revenue": row.revenue,
            "net_income": row.net_income,
            "operating_income": row.operating_income,
            "gross_profit": row.gross_profit,
            "total_assets": row.total_assets,
            "total_liabilities": row.total_liabilities,
            "stockholders_equity": row.stockholders_equity,
            "cash": row.cash_and_equivalents,
            "liabilities_effective": (
                row.total_liabilities
                if row.total_liabilities is not None
                else (
                    row.total_assets - row.stockholders_equity
                    if row.total_assets is not None
                    and row.stockholders_equity is not None
                    else None
                )
            ),
        }

    # ------------------------------------------------------------------
    # Historical S&P 500 membership
    # ------------------------------------------------------------------
    def historical_universe_available(self) -> bool:
        """True when FDB 0.4.0's ``sp500_constituents`` is present and loaded."""
        try:
            with self._get_connection().cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM sp500_constituents)")
                row = cur.fetchone()
            return bool(row and row.get("exists"))
        except Exception:  # noqa: BLE001 — missing table = not available
            return False

    def get_sp500_universe(self, as_of: date) -> list[str]:
        """Tickers that were S&P 500 members on ``as_of`` (half-open interval)."""
        as_of = _as_date(as_of) or as_of
        try:
            with self._get_connection().cursor() as cur:
                cur.execute(
                    """
                    SELECT ticker
                    FROM sp500_constituents
                    WHERE start_date <= %s
                      AND (end_date IS NULL OR end_date > %s)
                    ORDER BY ticker
                    """,
                    (as_of, as_of),
                )
                rows = cur.fetchall()
            return [str(row["ticker"]).upper() for row in rows if row.get("ticker")]
        except Exception:  # fall back to the current universe
            logger.debug("sp500_constituents read failed", exc_info=True)
            return []

    def get_sp500_universe_bounds(self) -> tuple[date | None, date | None]:
        """Earliest start and latest end/implicit date in the membership table."""
        try:
            with self._get_connection().cursor() as cur:
                cur.execute(
                    "SELECT MIN(start_date) AS first, "
                    "MAX(COALESCE(end_date, CURRENT_DATE)) AS last "
                    "FROM sp500_constituents"
                )
                row = cur.fetchone()
            return (
                _as_date(row.get("first")) if row else None,
                _as_date(row.get("last")) if row else None,
            )
        except Exception:  # noqa: BLE001
            return (None, None)
