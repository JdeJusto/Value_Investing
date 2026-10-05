"""Share counts, split ratios and per-share helpers.

Mixin for :class:`FinancialDatabaseRepository` (pure move).
"""

from __future__ import annotations

import math

from backend.repositories.fdb_concept_mapping import (
    _SPLIT_RATIO_CONCEPTS,
)


class SharesMixin:
    def _fetch_split_ratio_facts(self, company_id) -> list:
        """All ``StockSplitConversionRatio`` facts for a company.

        Returns ``[(period_end, ratio), ...]`` pairs from the XBRL facts (one
        per split; period_end = effective date, ratio = shares-after /
        shares-before). Empty list when the company reports no ratio facts —
        callers then keep the splits-unadjusted 1.0 factor.
        """
        if not company_id:
            return []
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT f.period_end, f.value
                    FROM financial_facts f
                    WHERE f.company_id = %s
                      AND f.concept = ANY(%s::text[])
                """,
                    (company_id, list(_SPLIT_RATIO_CONCEPTS)),
                )
                # RealDict rows iterate by KEY, so unpack them into plain
                # (period_end, ratio) tuples before returning.
                return [
                    (row.get("period_end"), row.get("value"))
                    for row in cur.fetchall()
                    if row is not None
                ]
        except Exception:  # noqa: BLE001 — degrade to 1.0 (as-reported shares)
            # instead of failing the ticker.
            return []

    @staticmethod
    def _shares_cache_key(fiscal_year: int, prefer_diluted: bool) -> str:
        """Shares are cached per year AND per share basis: the diluted and
        as-reported answers differ, and callers ask for both."""
        return f"{int(fiscal_year)}:{'diluted' if prefer_diluted else 'basic'}"

    def get_shares_outstanding(
        self,
        ticker: str,
        fiscal_year: int,
        prefer_diluted: bool = False,
    ) -> float | None:
        """Cached shares outstanding: per-year DB lookup, content-addressed.

        The answer only changes when the company's facts change, which is what
        the cache fingerprint tracks, so a valuation or validation run over
        several years reuses one query per (ticker, year, basis) instead of
        repeating it. ``None`` is a real answer (concept absent) and is cached
        too, so a small filer is not re-queried on every run.
        """
        cache = self._lookup_cache()
        if cache is None:
            return self._get_shares_outstanding_uncached(
                ticker, fiscal_year, prefer_diluted
            )
        fingerprint = cache.fingerprint_for(ticker)
        if fingerprint is None:
            return self._get_shares_outstanding_uncached(
                ticker, fiscal_year, prefer_diluted
            )
        from backend.services.analysis_cache import SECTION_SHARES

        key = self._shares_cache_key(fiscal_year, prefer_diluted)
        if cache._entry_present(ticker, fingerprint, SECTION_SHARES, key):
            value = cache.get_lookup(ticker, fingerprint, SECTION_SHARES, key)
            return float(value) if value is not None else None
        value = self._get_shares_outstanding_uncached(
            ticker, fiscal_year, prefer_diluted
        )
        cache.put_lookup(ticker, fingerprint, SECTION_SHARES, key, value)
        return value

    def _get_shares_outstanding_uncached(
        self,
        ticker: str,
        fiscal_year: int,
        prefer_diluted: bool = False,
    ) -> float | None:
        """Get shares outstanding for a ticker and fiscal year.

        Tries multiple concepts in order:
          1. WeightedAverageNumberOfSharesOutstandingDiluted /
             WeightedAverageNumberOfDilutedSharesOutstanding
          2. WeightedAverageNumberOfSharesOutstandingBasic
          3. CommonStockSharesOutstanding (point-in-time)
          4. WeightedAverageNumberOfSharesOutstanding

        Args:
            ticker: Company ticker symbol
            fiscal_year: Fiscal year
            prefer_diluted: When True try diluted weighted-average concepts
                first (best basis for diluted EPS); otherwise the as-reported
                end-of-period share count is preferred.

        Returns:
            Shares outstanding if available, None otherwise
        """
        end_of_period = [
            "CommonStockSharesOutstanding",
            "WeightedAverageNumberOfSharesOutstandingBasic",
            "WeightedAverageNumberOfSharesOutstanding",
            "WeightedAverageNumberOfSharesOutstandingDiluted",
            "WeightedAverageNumberOfDilutedSharesOutstanding",
        ]
        diluted = [
            "WeightedAverageNumberOfSharesOutstandingDiluted",
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            "CommonStockSharesOutstanding",
            "WeightedAverageNumberOfSharesOutstandingBasic",
        ]
        concepts_to_try = diluted if prefer_diluted else end_of_period
        try:
            # Get company ID from ticker
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return None

            conn = self._get_connection()
            candidate = None
            with conn.cursor() as cur:
                # Try multiple concepts, preferring the annual ('FY') fact with
                # the latest period_end (the actual fiscal-year-end figure).
                #
                # Duplicate rows for the same period_end come from later
                # filings restating the comparative column. Their magnitude
                # tells us which one to trust for per-share metrics:
                #   * ratio >= 10x — legacy thousands-tagged fact vs the true
                #     count (Ball 2009/2010: 187,572 vs 187,572,000). The
                #     larger value is authoritative.
                #   * small ratio — a stock-split restatement (Ball restated
                #     2015/2016 ~2x after its 2017 2:1 split). Keep the
                #     ORIGINAL (earliest-filled) disclosure: PriceService's
                #     split adjustment already carries the share count onto the
                #     current basis, so combining both would double count.
                def _pick(values, period_ends):
                    if not values:
                        return None
                    nums = [float(v) for v in values]
                    if (
                        len(nums) > 1
                        and period_ends[0] == period_ends[1]
                        and min(nums) > 0
                        and max(nums) / min(nums) >= 10.0
                    ):
                        return max(nums)
                    return nums[0]

                for concept in concepts_to_try:
                    cur.execute(
                        """
                        SELECT f.value, f.filing_date, f.period_end
                        FROM financial_facts f
                        WHERE f.company_id = %s
                          AND f.fiscal_year = %s
                          AND f.concept = %s
                          AND UPPER(f.fiscal_period) = 'FY'
                        ORDER BY (f.period_end - COALESCE(f.period_start, f.period_end)) DESC,
                                 f.period_end DESC NULLS LAST,
                                 f.filing_date ASC NULLS LAST
                        LIMIT 2
                    """,
                        (company_id, fiscal_year, concept),
                    )

                    rows = cur.fetchall()
                    candidate = (
                        _pick(
                            [r["value"] for r in rows if r["value"] is not None],
                            [r["period_end"] for r in rows if r["value"] is not None],
                        )
                        if rows
                        else None
                    )
                    if candidate is not None:
                        break

                # Fallback: no annual fact — accept any period (rare)
                if candidate is None:
                    for concept in concepts_to_try:
                        cur.execute(
                            """
                            SELECT f.value, f.filing_date, f.period_end
                            FROM financial_facts f
                            WHERE f.company_id = %s
                              AND f.fiscal_year = %s
                              AND f.concept = %s
                            ORDER BY (f.period_end - COALESCE(f.period_start, f.period_end)) DESC,
                                     f.filing_date ASC NULLS LAST
                            LIMIT 2
                        """,
                            (company_id, fiscal_year, concept),
                        )

                        rows = cur.fetchall()
                        candidate = (
                            _pick(
                                [r["value"] for r in rows if r["value"] is not None],
                                [
                                    r["period_end"]
                                    for r in rows
                                    if r["value"] is not None
                                ],
                            )
                            if rows
                            else None
                        )
                        if candidate is not None:
                            break

                # Legacy SEC filings (pre-2011) sometimes tag weighted-average
                # share counts in thousands while the cover-page share count is
                # correct (e.g. Ball Corp 2010 weighted-average basic = 180,746
                # but outstanding stood at 169,198,602). Detect the scale
                # mismatch against EntityCommonStockSharesOutstanding and repair
                # the candidate so per-share metrics are not inflated ~1000x.
                if candidate is not None and candidate > 0:
                    cur.execute(
                        """
                        SELECT f.value
                        FROM financial_facts f
                        WHERE f.company_id = %s
                          AND f.fiscal_year = %s
                          AND f.concept = 'EntityCommonStockSharesOutstanding'
                          AND UPPER(f.fiscal_period) = 'FY'
                        ORDER BY f.period_end DESC NULLS LAST
                        LIMIT 1
                    """,
                        (company_id, fiscal_year),
                    )

                    result = cur.fetchone()
                    anchor = (
                        float(result["value"])
                        if result and result["value"] is not None
                        else None
                    )
                    if anchor and anchor > 0:
                        ratio = anchor / candidate
                        # A legitimate weighted-average count never diverges
                        # from the end-of-period count by 100x+; this only
                        # happens when one side is unit-scaled.
                        if ratio >= 100.0:
                            scale = 10 ** round(math.log10(ratio))
                            candidate = candidate * scale

            # Implausibly small share counts (legacy thousands-tagged facts
            # with no anchor to repair against, e.g. Ball Corp 2008) are
            # unusable for per-share metrics — surface None instead of a
            # ~1000x-inflated EPS.
            if candidate is not None and candidate < 1_000_000:
                candidate = None

            return candidate

        except Exception:  # noqa: BLE001 — a DB failure reads as "unknown"
            return None

    def get_available_to_common_diluted_net_income(
        self, ticker: str, fiscal_year: int
    ) -> float | None:
        """Return net income available to common stockholders on a diluted
        basis (``NetIncomeLossAvailableToCommonStockholdersDiluted``) for the
        fiscal year, if filed.

        Some filers' diluted EPS uses a *diluted* attribution of net income
        (adding back assumed conversions of LLC units / dilutive securities)
        that differs from the basic available-to-common figure. Pairing that
        numerator with the diluted share count reproduces the as-reported
        diluted EPS exactly (e.g. Carvana 2025: 1,895M / 224.3M shares).

        Args:
            ticker: Company ticker symbol
            fiscal_year: Fiscal year

        Returns:
            Diluted available-to-common net income if found, None otherwise
        """
        try:
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return None

            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT f.value
                    FROM financial_facts f
                    WHERE f.company_id = %s
                      AND f.fiscal_year = %s
                      AND f.concept = 'NetIncomeLossAvailableToCommonStockholdersDiluted'
                      AND UPPER(f.fiscal_period) = 'FY'
                      AND f.period_end = (
                          SELECT MAX(f2.period_end)
                          FROM financial_facts f2
                          WHERE f2.company_id = f.company_id
                            AND f2.fiscal_year = %s
                            AND UPPER(f2.fiscal_period) = 'FY'
                            AND f2.concept IN (
                                'NetIncomeLoss',
                                'Revenues',
                                'SalesRevenueNet',
                                'SalesRevenueServicesNet',
                                'SalesRevenueGoodsNet',
                                'RevenueFromContractWithCustomerExcludingAssessedTax'
                            )
                      )
                    ORDER BY f.period_end DESC NULLS LAST
                    LIMIT 1
                """,
                    (company_id, fiscal_year, fiscal_year),
                )

                result = cur.fetchone()
                if result and result["value"] is not None:
                    return float(result["value"])
                return None

        except Exception:  # noqa: BLE001 — a DB failure reads as "unknown"
            return None
