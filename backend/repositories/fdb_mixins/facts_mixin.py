"""Facts reads (years, facts, normalized records).

Mixin for :class:`FinancialDatabaseRepository` (pure move).
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
)
from backend.repositories.fdb_mixins.helpers import (
    _as_date,
    _cumulative_split_multiplier,
)


class FactsMixin:
    def get_by_year(self, ticker: str, fiscal_year: int) -> NormalizedFinancials | None:
        """Return the normalized record for a given fiscal year, if stored."""
        try:
            # Get company ID from ticker
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return None

            conn = self._get_connection()
            with conn.cursor() as cur:
                # Get financial facts for this company/year directly using company_id.
                # Only annual ('FY') facts are used: the fiscal_year bucket also
                # holds quarterly YTD facts and the comparative years embedded in
                # the latest 10-K, so filtering to 'FY' is what makes each value
                # represent a completed fiscal year (see _normalize_financial_facts
                # for the max-period_end dedup).
                cur.execute(
                    """
                    SELECT
                        f.concept,
                        f.value,
                        f.unit,
                        f.fiscal_year,
                        f.fiscal_period,
                        f.period_end,
                        f.period_start
                    FROM financial_facts f
                    WHERE f.company_id = %s
                      AND f.fiscal_year = %s
                      AND UPPER(f.fiscal_period) = 'FY'
                """,
                    (company_id, fiscal_year),
                )

                facts = cur.fetchall()

                if not facts:
                    return None

                # Split adjustment: restate this year's as-reported shares on
                # today's basis (product of split ratios effective after the
                # fiscal year end). 1.0 when the filer reports no ratio.
                fy_end = max(
                    (pe for pe in (_as_date(f.get("period_end")) for f in facts) if pe),
                    default=None,
                )
                split_factor = _cumulative_split_multiplier(
                    fy_end, self._fetch_split_ratio_facts(company_id)
                )

                # Normalize the facts
                statements = self._normalize_financial_facts(
                    facts, bucket_year=fiscal_year
                )
                statements = self._calculate_derived_fields(statements)

                # Build and return NormalizedFinancials
                return self._build_normalized_financials(
                    ticker=ticker.upper(),
                    fiscal_year=fiscal_year,
                    statements=statements,
                    split_adjustment_factor=split_factor,
                    sector=self._get_company_sector(ticker),
                )

        except Exception:  # noqa: BLE001 — a failure degrades to None so the caller falls back
            # In case of any error, return None to let fallback handle it
            return None

    def list_years(
        self, ticker: str, max_years: int | None = None
    ) -> list[NormalizedFinancials]:
        """Return the best record per year for a ticker, most recent first.

        Results are cached for the lifetime of this repository instance so the
        two calls ``analyze`` makes per ticker (``_load_history`` and
        ``_data_reliability``) re-use one query + normalization instead of
        fetching the full FY history twice. Only non-empty results are cached
        and ``invalidate_list_cache``/``upsert*`` clear a ticker when its data
        changes, so a deliberate refresh never serves stale fundamentals.

        ``max_years`` limits the read to the newest N fiscal years and
        bypasses the instance cache (a capped list must never be served to a
        caller that wants the full history).
        """
        ticker = ticker.upper()
        if max_years is None:
            cached = self._list_cache_get(ticker)
            if cached is not None:
                return list(cached)

        if max_years is None:
            rows = self._list_years_uncached(ticker)
        else:
            rows = self._list_years_uncached(ticker, max_years=max_years)

        if max_years is not None:
            return rows

        if rows:
            self._list_cache_set(ticker, rows)
        else:
            # Negative lookups are never cached: a loader/sync may populate the
            # company in between and the next read must see the fresh data.
            self.invalidate_list_cache(ticker)
        return rows

    def list_all_facts(
        self,
        ticker: str,
        fiscal_period: str = "FY",
        max_years: int | None = None,
    ) -> list[dict]:
        """Every stored fact for a ticker as flat dicts (no VO mapping).

        Unlike ``list_years`` (which normalizes facts into the mapped
        statement fields), this returns *all* XBRL concepts in the company's
        history for the requested fiscal period, so the Financials view can
        show the complete picture as stored. Rows carry ``{concept,
        fiscal_year, fiscal_period, value, unit, period_end, namespace,
        frame}``; ``value`` stays numeric (callers format for display).

        ``max_years`` pushes the history cap into SQL (newest N fiscal
        years), matching ``list_years``. A broken listing degrades to [].
        """
        ticker = ticker.upper()
        try:
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return []
            sql = """
                SELECT
                    f.concept,
                    f.fiscal_year,
                    f.fiscal_period,
                    f.value,
                    f.unit,
                    f.period_end,
                    f.namespace,
                    f.frame
                FROM financial_facts f
                WHERE f.company_id = %s
                  AND UPPER(f.fiscal_period) = %s
            """
            params: list = [company_id, fiscal_period.upper()]
            conn = self._get_connection()
            with conn.cursor() as cur:
                if max_years is not None:
                    min_year = self._min_fiscal_year(cur, company_id, max_years)
                    if min_year is not None:
                        sql += " AND f.fiscal_year >= %s"
                        params.append(min_year)
                sql += (
                    " ORDER BY f.concept ASC, f.fiscal_year DESC,"
                    " f.period_end DESC NULLS LAST"
                )
                cur.execute(sql, tuple(params))
                return [dict(row) for row in cur.fetchall()]
        except Exception:  # noqa: BLE001 — a broken listing degrades to no facts
            return []

    @staticmethod
    def _min_fiscal_year(cur, company_id: str, max_years: int) -> int | None:
        """Oldest fiscal year a ``max_years`` cap should read (newest N)."""
        cur.execute(
            "SELECT MAX(fiscal_year) FROM financial_facts "
            "WHERE company_id = %s AND UPPER(fiscal_period) = 'FY'",
            (company_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        latest = next(iter(row.values()))
        return None if latest is None else latest - max_years + 1

    def _list_years_uncached(
        self, ticker: str, max_years: int | None = None
    ) -> list[NormalizedFinancials]:
        """The uncached list_years implementation (see ``list_years``).

        All *annual* (FY) facts for the company are fetched in a single query
        and bucketed by fiscal year, replacing the old per-year ``get_by_year``
        round-trips (3 + 2×N queries per ticker) with 2 queries. The rows fed
        to ``_normalize_financial_facts`` per year are identical to what
        ``get_by_year`` produced, so the reconstructed records do not change.

        ``max_years`` pushes the history cap into SQL (newest N fiscal years)
        so neither the transfer nor the per-year normalization pays for the
        full archive; the screener reads ~10 years instead of ~16.
        """
        try:
            # Get company ID from ticker (same as get_by_year)
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return []

            # Company sector is per-company metadata fetched once per ticker
            # and stamped on every reconstructed year.
            company_sector = self._get_company_sector(ticker)

            conn = self._get_connection()
            facts = []
            with conn.cursor() as cur:
                # Only annual ('FY') facts are used: the fiscal_year bucket also
                # holds quarterly YTD facts and the comparative years embedded in
                # the latest 10-K, so filtering to 'FY' is what makes each value
                # represent a completed fiscal year (see _normalize_financial_facts
                # for the max-period_end dedup).
                sql = """
                    SELECT
                        f.concept,
                        f.value,
                        f.unit,
                        f.fiscal_year,
                        f.fiscal_period,
                        f.period_end,
                        f.period_start
                    FROM financial_facts f
                    WHERE f.company_id = %s
                      AND UPPER(f.fiscal_period) = 'FY'
                """
                params: list = [company_id]
                if max_years is not None:
                    min_year = self._min_fiscal_year(cur, company_id, max_years)
                    if min_year is not None:
                        sql += " AND f.fiscal_year >= %s"
                        params.append(min_year)
                cur.execute(sql, tuple(params))
                facts = cur.fetchall()

            if not facts:
                return []

            by_year: dict[int, list] = {}
            for row in facts:
                by_year.setdefault(row["fiscal_year"], []).append(row)

            # One query for every split ratio the company ever reported; each
            # year's factor is computed from it (pure function), keeping the
            # methodology payload hermetic — the factor is data, not a price.
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
                        ticker=ticker.upper(),
                        fiscal_year=year,
                        statements=statements,
                        split_adjustment_factor=split_factor,
                        sector=company_sector,
                    )
                    if financials is not None:
                        results.append(financials)
                except Exception:  # noqa: BLE001, S112 — one bad year must not drop the rest
                    continue
            return results

        except Exception:  # noqa: BLE001 — a broken listing degrades to an empty history
            return []

    def list_all(
        self, ticker: str, max_years: int | None = None
    ) -> list[NormalizedFinancials]:
        """Return every stored record (all sources), year desc.

        ``max_years`` caps the history to the newest N fiscal years (the
        screener needs ~10, not the full ~16-year archive); ``None`` keeps
        every year.
        """
        # For Financial-DataBase, we primarily have SEC EDGAR data
        # and we don't have multiple sources, so we return the same as list_years.
        if max_years is None:
            return self.list_years(ticker)
        return self.list_years(ticker, max_years=max_years)

    _EMPTY_ROW_FIELDS = (
        "revenue",
        "net_income",
        "total_assets",
        "shares_outstanding",
    )

    @staticmethod
    def _row_is_empty(row: NormalizedFinancials) -> bool:
        """True when a row has none of the core fields any analysis needs.

        A fiscal_year bucket rebuilt from stray facts only (see
        ``_EMPTY_ROW_FIELDS``) is all-empty for every methodology and must be
        skipped instead of anchoring the "latest year" read.
        """
        return all(
            getattr(row, field) is None for field in FactsMixin._EMPTY_ROW_FIELDS
        )

    def get_best_available(
        self, ticker: str, max_years: int | None = None
    ) -> list[NormalizedFinancials]:
        """Return the most consistent usable history for a ticker.

        For Financial-DataBase, we assume SEC EDGAR data is consistently
        high quality, so we return all available years — except all-empty
        ones (``_row_is_empty``). An all-empty row is an in-progress
        fiscal-year bucket that only picked up stray non-income facts; no
        analysis must read it as the latest year. Returns [] when no usable
        row exists. ``max_years`` caps the history to the newest N fiscal
        years (see ``list_years``).
        """
        rows = self.list_all(ticker)
        if max_years is not None:
            rows = self.list_all(ticker, max_years=max_years)
        return [row for row in rows if not self._row_is_empty(row)]

    def has_data(self, ticker: str) -> bool:
        """True if at least one record exists for the ticker."""
        try:
            # Get company ID from ticker
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return False

            # Get company identifiers to get the CIK for querying financial facts
            conn = self._get_connection()
            with conn.cursor() as cur:
                # Get the CIK for this company
                cur.execute(
                    """
                    SELECT ci.identifier_value as cik
                    FROM company_identifiers ci
                    WHERE ci.company_id = %s
                      AND ci.identifier_type = 'CIK'
                      AND ci.provider_id = (SELECT id FROM data_providers WHERE name = 'SEC EDGAR')
                """,
                    (company_id,),
                )

                cik_result = cur.fetchone()
                if not cik_result:
                    return False

                # Check if there's any financial data for this company
                cur.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM financial_facts f
                    WHERE f.company_id = %s
                """,
                    (company_id,),
                )

                result = cur.fetchone()
                return result["count"] > 0 if result else False

        except Exception:  # noqa: BLE001 — a DB failure answers as "not available"
            return False

    def get_normalized_financials(
        self, ticker: str, fiscal_year: int
    ) -> NormalizedFinancials | None:
        """Get normalized financials for a ticker and fiscal year.

        This method is an alias for get_by_year to match the FinancialRepository interface.

        Args:
            ticker: Company ticker symbol
            fiscal_year: Fiscal year

        Returns:
            NormalizedFinancials object if found, None otherwise
        """
        return self.get_by_year(ticker, fiscal_year)

    def _lookup_cache(self):
        """The shared AnalysisCache, or None when no cache is wired in."""
        cache = getattr(self, "_analysis_cache", None)
        return cache if getattr(cache, "enabled", False) else None
