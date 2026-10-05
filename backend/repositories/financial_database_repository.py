"""Financial Database repository implementation for Value Investing.

This repository connects to the Financial-DataBase PostgreSQL database and
implements the FinancialRepository interface by querying the normalized
financial facts and reconstructing NormalizedFinancials objects.
"""

from __future__ import annotations

import hashlib
import math
import os
import threading
from datetime import UTC, date, datetime

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.value_objects.financials_normalized import (
    ANNUAL_PERIOD,
    NormalizedFinancials,
    ProviderName,
)
from backend.repositories.fdb_concept_mapping import (
    _COMMON_ONLY_DIVIDEND_CONCEPTS,
    _SPLIT_RATIO_CONCEPTS,
    BALANCE_SHEET_CONCEPTS,
    CASH_FLOW_CONCEPT_RANK,
    CASH_FLOW_CONCEPTS,
    CORE_STATEMENT_CONCEPTS,
    DEBT_CURRENT_RANK,
    DEBT_NONCURRENT_RANK,
    INCOME_CONCEPT_RANK,
    INCOME_STATEMENT_CONCEPTS,
    _income_convention,
)


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


class FinancialDatabaseRepository(FinancialRepository):
    """Repository that reads from Financial-DataBase PostgreSQL database.

    This repository queries the financial_facts table and reconstructs
    NormalizedFinancials objects by mapping XBRL concepts to financial
    statement fields.
    """

    def __init__(self, database_url: str | None = None):
        """Initialize the repository with database connection.

        Args:
            database_url: PostgreSQL connection string. If None, uses
                         FINANCIAL_DATABASE_URL environment variable or
                         default to financial_database instance.
        """
        if database_url is None:
            database_url = os.environ.get(
                "FINANCIAL_DATABASE_URL",
                # Local development default; override with the env var.
                "postgresql://financial:test@localhost:5432/financial_database",
            )

        self.database_url = database_url
        # psycopg2 connections are not thread-safe: when analysis runs in a
        # thread pool each worker needs its own lazily-created connection. All
        # connections opened by *any* thread are tracked so close() can tear
        # them down together.
        self._local = threading.local()
        self._connections: set = set()
        self._connections_lock = threading.Lock()

        # Per-run fundamentals cache. ``analyze`` fetches the full FY history
        # twice per ticker (list_years via _load_history and again via
        # _data_reliability's list_all); both funnel through list_years, so a
        # simple run-scoped cache removes the redundant round-trip +
        # normalization. Only NON-EMPTY results are cached (a deliberate
        # refresh could otherwise serve stale data for a currently-empty
        # ticker), and writes invalidate the affected ticker.
        self._list_cache: dict[str, list[NormalizedFinancials]] = {}
        self._list_cache_lock = threading.Lock()

        # Optional shared AnalysisCache. When present, the per-year DB
        # lookups (shares outstanding, fiscal-year-end) are served from it
        # under the same content-addressed fingerprint as the fundamentals,
        # so a valuation or validation run stops re-querying facts that have
        # not changed. Injected by attach_analysis_cache() to avoid an
        # import cycle (the cache needs this repository for fingerprints).
        self._analysis_cache = None

    def attach_analysis_cache(self, cache) -> FinancialDatabaseRepository:
        """Wire the shared analysis cache (per-year lookups) and return self."""
        self._analysis_cache = cache
        return self

    # ------------------------------------------------------------------
    # per-run list_years cache helpers
    # ------------------------------------------------------------------
    def _list_cache_get(self, ticker: str) -> list[NormalizedFinancials] | None:
        with self._list_cache_lock:
            return self._list_cache.get(ticker)

    def _list_cache_set(self, ticker: str, rows: list[NormalizedFinancials]) -> None:
        with self._list_cache_lock:
            self._list_cache[ticker] = list(rows)

    def invalidate_list_cache(self, ticker: str) -> None:
        """Drop the cached fundamentals for one ticker (after a refresh/write)."""
        with self._list_cache_lock:
            self._list_cache.pop(ticker, None)

    def clear_list_cache(self) -> None:
        """Drop every cached fundamentals entry (call before a data sync)."""
        with self._list_cache_lock:
            self._list_cache.clear()

    def _get_connection(self):
        """Get or create a connection for the *current* thread.

        Every worker thread receives its own connection (created on first
        use) so parallel analysis never shares a psycopg2 connection across
        threads.
        """
        conn = getattr(self._local, "connection", None)
        if conn is None or conn.closed:
            conn = psycopg2.connect(
                self.database_url,
                cursor_factory=RealDictCursor,
            )
            self._local.connection = conn
            with self._connections_lock:
                self._connections.add(conn)
        return conn

    def close(self):
        """Close every connection this repository opened (any thread)."""
        with self._connections_lock:
            connections = list(self._connections)
            self._connections.clear()
        for conn in connections:
            try:
                if not conn.closed:
                    conn.close()
            except Exception:  # noqa: BLE001, S110 — best-effort teardown
                pass
        self._local.connection = None

    def available(self) -> bool:
        """Check if the Financial-DataBase is available."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
        except Exception:  # noqa: BLE001 — a DB failure answers as "not available"
            return False

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

    def get_company_name(self, ticker: str) -> str | None:
        """Company legal name by ticker, or None when unknown.

        Reads only metadata (companies + company_identifiers); no prices.
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.legal_name
                    FROM company_identifiers ci
                    JOIN companies c ON c.id = ci.company_id
                    WHERE ci.identifier_type = 'TICKER'
                      AND ci.identifier_value = %s
                    LIMIT 1
                    """,
                    (str(ticker).upper(),),
                )
                row = cur.fetchone()
                return row["legal_name"] if row else None
        except Exception:  # noqa: BLE001 — a DB failure reads as "unknown"
            return None

    def has_active_listing(self, ticker: str) -> bool | None:
        """Is ``ticker`` a known listed company? Tri-state for classification.

        Returns True when the ticker maps to an active exchange listing (or a
        TICKER identifier of a known company), False when the database has no
        such listing at all (a universe/mapping gap), and None when the
        lookup itself cannot be answered (database unavailable). Used by
        PriceService.classify_price_failure to separate `mapping` failures
        from `delisted` ones. Metadata-only — never touches price data.
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM company_listings
                    WHERE UPPER(ticker) = %s AND is_active
                    LIMIT 1
                    """,
                    (str(ticker).upper(),),
                )
                if cur.fetchone() is not None:
                    return True
                cur.execute(
                    """
                    SELECT 1 FROM company_identifiers
                    WHERE identifier_type = 'TICKER'
                      AND UPPER(identifier_value) = %s
                    LIMIT 1
                    """,
                    (str(ticker).upper(),),
                )
                return cur.fetchone() is not None
        except Exception:  # noqa: BLE001 — a DB failure reads as "unknown"
            return None

    def get_cik(self, ticker: str) -> str | None:
        """SEC CIK for a ticker, or None when the company is not in the DB.

        Returns the CIK identifier stored on the company the ticker maps to.
        Foreign filers (ASML, NVO, ...) commonly have no US CIK here.
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ci.identifier_value as cik
                    FROM company_identifiers ct
                    JOIN company_identifiers ci ON ci.company_id = ct.company_id
                    WHERE ct.identifier_type = 'TICKER'
                      AND UPPER(ct.identifier_value) = %s
                      AND UPPER(ci.identifier_type) = 'CIK'
                    ORDER BY UPPER(ci.provider_id::text) DESC
                    LIMIT 1
                    """,
                    (str(ticker).upper(),),
                )
                row = cur.fetchone()
                return row["cik"] if row else None
        except Exception:  # noqa: BLE001 — a DB failure reads as "unknown"
            return None

    def _get_company_id_by_cik(self, cik: str) -> str | None:
        """Get company ID from CIK.

        Args:
            cik: Central Index Key (10-digit string)

        Returns:
            Company UUID if found, None otherwise
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.id
                    FROM companies c
                    JOIN company_identifiers ci ON c.id = ci.company_id
                    JOIN data_providers dp ON ci.provider_id = dp.id
                    WHERE UPPER(ci.identifier_type) = 'CIK'
                      AND UPPER(ci.identifier_value) = %s
                      AND UPPER(dp.name) = 'SEC EDGAR'
                """,
                    (cik.upper(),),
                )
                result = cur.fetchone()
                return str(result["id"]) if result else None
        except Exception:  # noqa: BLE001 — a DB failure reads as "unknown"
            return None

    def _get_company_id_by_ticker(self, ticker: str) -> str | None:
        """Get company ID from ticker symbol.

        Args:
            ticker: Company ticker symbol (e.g., 'AAPL')

        Returns:
            Company UUID if found, None otherwise
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.id
                    FROM companies c
                    JOIN company_identifiers ci ON c.id = ci.company_id
                    WHERE UPPER(ci.identifier_type) = 'TICKER'
                      AND UPPER(ci.identifier_value) = %s
                """,
                    (ticker.upper(),),
                )
                result = cur.fetchone()
                return str(result["id"]) if result else None
        except Exception:  # noqa: BLE001 — a DB failure reads as "unknown"
            return None

    def _get_company_sector(self, ticker: str) -> str | None:
        """Company sector label from the Financial-DataBase metadata.

        Reads only ``companies.sector`` (populated by the Financial-DataBase
        ``scripts/populate_sector_industry.py`` enrichment; None when unknown
        or not yet populated). Metadata only — never touches prices.
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.sector
                    FROM companies c
                    JOIN company_identifiers ci ON c.id = ci.company_id
                    WHERE UPPER(ci.identifier_type) = 'TICKER'
                      AND UPPER(ci.identifier_value) = %s
                """,
                    (ticker.upper(),),
                )
                result = cur.fetchone()
                return result["sector"] if result else None
        except Exception:  # noqa: BLE001 — a DB failure reads as "unknown"
            return None

    def _get_listing_id_by_cik(self, cik: str) -> str | None:
        """Get listing ID for a company's primary listing.

        Args:
            cik: Central Index Key (10-digit string)

        Returns:
            Listing UUID if found, None otherwise
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT cl.id
                    FROM company_listings cl
                    JOIN companies c ON cl.company_id = c.id
                    JOIN company_identifiers ci ON c.id = ci.company_id
                    JOIN data_providers dp ON ci.provider_id = dp.id
                    WHERE UPPER(ci.identifier_type) = 'CIK'
                      AND UPPER(ci.identifier_value) = %s
                      AND UPPER(dp.name) = 'SEC EDGAR'
                      AND cl.is_active = TRUE
                    ORDER BY cl.created_at
                    LIMIT 1
                """,
                    (cik.upper(),),
                )
                result = cur.fetchone()
                return str(result["id"]) if result else None
        except Exception:  # noqa: BLE001 — a DB failure reads as "unknown"
            return None

    def _normalize_financial_facts(
        self, facts: list[dict], bucket_year: int | None = None
    ) -> dict:
        """Normalize a list of financial facts into financial statement components.

        Args:
            facts: List of financial fact dictionaries from database
            bucket_year: Fiscal year this facts list is supposed to represent.
                When given, rows whose ``period_end`` falls outside that
                calendar year are dropped so the newest-period_end dedup cannot
                pick a value from a neighbouring year (see below).

        Returns:
            Dictionary with financial statement data organized by statement type
        """
        # Initialize statement containers
        income_data = {}
        balance_data = {}
        cash_flow_data = {}
        dividends_paid_concept: str | None = None

        # A fiscal-year bucket can hold facts from other years: the latest 10-K
        # embeds its comparatives, and a sync may tag the SAME filing under two
        # different fiscal_years (e.g. a Jan-31 fiscal-year-end company whose
        # 10-K was ingested as both FY2025 and FY2026). Each bucket is only
        # responsible for the rows whose period_end falls within the labelled
        # year; dropping the rest keeps a next-year value from winning the
        # newest-period_end dedup and keeps as-of-date cover-page facts (like
        # EntityCommonStockSharesOutstanding) out of the balance snapshot. That
        # filter runs in the single precompute pass below (same walk that
        # builds the sort keys, so each fact parses its dates only once).

        # A fiscal-year bucket stores the latest 10-K plus its comparative
        # years (each fact carries its own period_start/period_end), and some
        # elements are reported both quarterly and year-to-date with the same
        # period_end. Order candidates so the true annual figure wins:
        #   1. longest period span (the ANNUAL fact; 10-K supplemental
        #      quarterly tables are re-tagged 'FY' by SEC, so a quarter can
        #      carry a LATER period_end than the real annual figure — e.g.
        #      Salesforce's Jan-31 fiscal year),
        #   2. newest period_end (the target comparative year),
        #   3. preferred concept for the field (e.g. 'Revenues' over
        #      RevenueFromContractWithCustomerExcludingAssessedTax),
        #   4. earliest period_start (longest cumulative duration).
        def _date_ord(value):
            if value is None:
                return 0
            if isinstance(value, date):
                return value.toordinal()
            try:
                return date.fromisoformat(str(value)[:10]).toordinal()
            except (ValueError, TypeError):
                return 0

        # Precompute each fact's sort key ONCE, before sorting. The previous
        # implementation re-parsed the two ISO dates inside every comparison
        # of sorted() (and re-parsed period_end again in the bucket filter),
        # which dominated the CPU time of large fact buckets. Each row now
        # parses period_end/period_start a single time.
        keyed = []
        for f in facts:
            pe = f.get("period_end")
            ps = f.get("period_start")
            pe_ord = _date_ord(pe)
            ps_ord = _date_ord(ps)
            concept = f.get("concept") or ""
            key = (
                pe_ord - ps_ord if pe is not None and ps is not None else 0,
                pe_ord,
                -INCOME_CONCEPT_RANK.get(
                    concept, CASH_FLOW_CONCEPT_RANK.get(concept, 10**9)
                ),
                -ps_ord,
            )
            year = date.fromordinal(pe_ord).year if pe_ord else None
            keyed.append(((key, year), f))

        if bucket_year is not None:
            year_rows = [f for ((_key, year), f) in keyed if year == bucket_year]
            if year_rows:
                keyed = [entry for entry in keyed if entry[0][1] == bucket_year]

        keyed.sort(key=lambda entry: entry[0][0], reverse=True)
        facts = [f for _, f in keyed]
        # The newest balance-sheet comparative drives total-debt aggregation.
        # Cover-page / as-of facts (e.g. EntityCommonStockSharesOutstanding,
        # which post-dates the fiscal year end) are not part of the balance
        # snapshot and must not lift MAX(): doing so would drop every balance
        # line, leaving total debt empty.
        max_pe = next(
            (
                f.get("period_end")
                for f in facts
                if f.get("period_end") is not None
                and f.get("concept") in BALANCE_SHEET_CONCEPTS
            ),
            None,
        )

        # Banks/brokers present a net-of-interest top line. Capture their
        # interest + non-interest income so their revenue can be reconstructed
        # when no net-revenue tag is filed.
        bank_interest = None
        bank_noninterest = None
        # REIT rental income (see the value-based override below).
        rental_income = None
        # R&D filed under the ExcludingAcquiredInProcessCost tag (JNJ keeps
        # its substantive line here; see the dominance override at the end).
        rnd_excluding = None
        # Best current / non-current debt figure within the newest comparative
        # (concept-priority single pick per portion, see DEBT_*_PRIORITY).
        debt_current = None
        debt_noncurrent = None

        # Process each fact
        for fact in facts:
            concept = fact["concept"]
            value = float(fact["value"]) if fact["value"] is not None else None

            # Skip if no value
            if value is None:
                continue

            # Map to income statement
            if concept in INCOME_STATEMENT_CONCEPTS:
                field_name = INCOME_STATEMENT_CONCEPTS[concept]
                if concept == "OperatingLeaseLeaseIncome" and rental_income is None:
                    rental_income = value
                if (
                    field_name == "research_development"
                    and concept
                    == "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"
                    and rnd_excluding is None
                ):
                    rnd_excluding = value
                # Handle duplicates by taking the first fact ordered above
                if field_name not in income_data or income_data[field_name] is None:
                    income_data[field_name] = value
                    if field_name == "net_income":
                        income_data["net_income_convention"] = _income_convention(
                            concept
                        )

            # Map to balance sheet
            elif (
                concept in BALANCE_SHEET_CONCEPTS
                or concept in DEBT_CURRENT_RANK
                or concept in DEBT_NONCURRENT_RANK
            ):
                field_name = BALANCE_SHEET_CONCEPTS.get(concept, "total_debt")
                # Total debt: take the current and non-current portions from the
                # SAME (newest) comparative, preferring one tag per portion so
                # equivalent aliases are not double counted.
                if (
                    field_name == "total_debt"
                    and max_pe is not None
                    and fact.get("period_end") != max_pe
                ):
                    continue
                if field_name == "total_debt":
                    cur_rank = DEBT_CURRENT_RANK.get(concept)
                    noncur_rank = DEBT_NONCURRENT_RANK.get(concept)
                    if cur_rank is not None and (
                        debt_current is None or cur_rank < debt_current[1]
                    ):
                        debt_current = (value, cur_rank)
                    elif noncur_rank is not None and (
                        debt_noncurrent is None or noncur_rank < debt_noncurrent[1]
                    ):
                        debt_noncurrent = (value, noncur_rank)
                else:
                    # Handle duplicates by taking the newest-comparative value
                    if (
                        field_name not in balance_data
                        or balance_data[field_name] is None
                    ):
                        balance_data[field_name] = value

            # Map to cash flow
            elif concept in CASH_FLOW_CONCEPTS:
                field_name = CASH_FLOW_CONCEPTS[concept]
                # Handle capital expenditure (make positive)
                if field_name == "capital_expenditure" and value is not None:
                    value = abs(value)  # Ensure positive

                # Handle duplicates by taking the newest-comparative value
                if (
                    field_name not in cash_flow_data
                    or cash_flow_data[field_name] is None
                ):
                    cash_flow_data[field_name] = value
                    if field_name == "dividends_paid":
                        dividends_paid_concept = concept

            # Track bank top-line components (not part of the standard mapping)
            elif concept == "InterestIncomeExpenseNet" and bank_interest is None:
                bank_interest = value
            elif concept == "NoninterestIncome" and bank_noninterest is None:
                bank_noninterest = value
            elif concept == "OperatingLeaseLeaseIncome" and rental_income is None:
                rental_income = value

        # Combine the current + non-current debt portions (single preferred tag
        # each) into total_debt. Absent both, the field stays unset.
        if debt_current is not None or debt_noncurrent is not None:
            balance_data["total_debt"] = (debt_current[0] if debt_current else 0.0) + (
                debt_noncurrent[0] if debt_noncurrent else 0.0
            )

        # Most filers present operating income (OperatingIncomeLoss) with no
        # separate EBIT tag; treat the two as equivalent so the EBIT-based
        # multiples (EV/EBIT, ROIC) keep working when only operating income is
        # filed.
        if (
            income_data.get("ebit") is None
            and income_data.get("operating_income") is not None
        ):
            income_data["ebit"] = income_data["operating_income"]

        # Gross profit = revenue - cost of revenue is the standard US-GAAP
        # identity, used when a filer does not tag GrossProfit directly. GM
        # last filed the tag in FY2012 and T stopped after the 2023 restatement,
        # but their cost lines (CostOfGoodsAndServicesSold / CostOfRevenue)
        # remain tagged for earlier years, so the margin series is kept instead
        # of dropped. Never overrides a filed figure (fires only when absent).
        if (
            income_data.get("gross_profit") is None
            and income_data.get("revenue") is not None
            and income_data.get("cogs") is not None
        ):
            income_data["gross_profit"] = income_data["revenue"] - income_data["cogs"]

        # REITs whose rental income is the whole top line (no revenue tag filed,
        # or only a small contract-revenue tag) report it as OperatingLease
        # LeaseIncome. Prefer the rental figure when it dominates whatever
        # contract-revenue tag was picked (e.g. CPT's 1.57B rental vs a 13M
        # contract tag) while leaving e.g. DD (6.85B sales vs 74M rental)
        # untouched. A non-positive rental figure never replaces a real top
        # line.
        if (
            rental_income is not None
            and rental_income > 0
            and (
                income_data.get("revenue") is None
                or rental_income > income_data["revenue"]
            )
        ):
            income_data["revenue"] = rental_income

        # Banks/brokers report a net-of-interest top line. When both
        # components exist, reconstruct revenue as their sum — but only when
        # the pair *dominates* whatever revenue tag was picked (mirrors the
        # REIT rule). A filer that reports a genuine, larger net-revenue tag
        # (some financial holding companies file `Revenues`) must never have
        # it clobbered by a smaller or non-positive reconstructed total; a
        # small incidental interest+non-interest pair must not shadow a
        # manufacturer's real sales either (e.g. 7M pair vs 1,000M Revenues).
        if bank_interest is not None and bank_noninterest is not None:
            bank_total = bank_interest + bank_noninterest
            current_rev = income_data.get("revenue")
            if bank_total > 0 and (current_rev is None or bank_total > current_rev):
                income_data["revenue"] = bank_total

        # JNJ's substantive R&D line lives under the ExcludingAcquiredInProcessCost
        # tag while its plain ResearchAndDevelopmentExpense tag only holds a
        # residual; other filers (AAPL, MSFT) report the plain tag only. When
        # both tags are present in the bucket keep the more complete (larger)
        # figure so a residual tag cannot read as 'no/low R&D'. Mirrors the
        # REIT/bank dominance overrides above.
        if rnd_excluding is not None and (
            income_data.get("research_development") is None
            or rnd_excluding > income_data["research_development"]
        ):
            income_data["research_development"] = rnd_excluding

        # A common-only cash dividend tag already excludes preferred
        # dividends; subtracting the income-statement preferred figure again
        # would double-count it (WFC/USB file PaymentsOfDividendsCommonStock
        # plus a preferred tag). Only keep it when the total tag won.
        if dividends_paid_concept in _COMMON_ONLY_DIVIDEND_CONCEPTS:
            income_data["preferred_dividends"] = None

        return {
            "income": income_data,
            "balance": balance_data,
            "cash_flow": cash_flow_data,
        }

    def _calculate_derived_fields(self, statements: dict) -> dict:
        """Calculate derived fields like working capital and free cash flow.

        Args:
            statements: Dictionary with income, balance, cash_flow data

        Returns:
            Updated statements dictionary with derived fields calculated
        """
        cash_flow = statements["cash_flow"]

        # Calculate working capital: Current Assets - Current Liabilities
        # Since we don't have current assets/liabilities directly,
        # we'll approximate or skip for now
        # TODO: Add proper current assets/liabilities concept mapping

        # Calculate free cash flow: Operating Cash Flow - Capital Expenditure
        if (
            cash_flow.get("operating_cash_flow") is not None
            and cash_flow.get("capital_expenditure") is not None
        ):
            cash_flow["free_cash_flow"] = (
                cash_flow["operating_cash_flow"] - cash_flow["capital_expenditure"]
            )

        return statements

    def _build_normalized_financials(
        self,
        ticker: str,
        fiscal_year: int,
        statements: dict,
        loaded_at: datetime | None = None,
        split_adjustment_factor: float = 1.0,
        sector: str | None = None,
    ) -> NormalizedFinancials:
        """Build a NormalizedFinancials object from statement data.

        Args:
            ticker: Company ticker symbol
            fiscal_year: Fiscal year
            statements: Dictionary with income, balance, cash_flow data
            loaded_at: When this data was loaded (defaults to now)
            split_adjustment_factor: Multiplier restating this year's
                as-reported shares on today's post-split basis (see
                ``_cumulative_split_multiplier``); 1.0 when unknown.
            sector: Company sector label from ``companies.sector`` (None when
                the metadata layer does not supply one).

        Returns:
            NormalizedFinancials object
        """
        if loaded_at is None:
            loaded_at = datetime.now(UTC)

        income = statements["income"]
        balance = statements["balance"]
        cash_flow = statements["cash_flow"]

        # The statement dataclasses (IncomeStatement/BalanceSheet/
        # CashFlowStatement) are intentionally not materialized here: the
        # NormalizedFinancials value object below carries every field the
        # analysis layer reads, and the intermediate objects were never used.
        return NormalizedFinancials(
            ticker=ticker,
            fiscal_year=fiscal_year,
            # Income statement
            revenue=income.get("revenue"),
            cogs=income.get("cogs"),
            gross_profit=income.get("gross_profit"),
            operating_income=income.get("operating_income"),
            ebit=income.get("ebit"),
            ebitda=income.get("ebitda"),
            net_income=income.get("net_income"),
            net_income_convention=income.get("net_income_convention"),
            interest_expense=income.get("interest_expense"),
            tax_provision=income.get("tax_provision"),
            pretax_income=income.get("pretax_income"),
            # Balance sheet
            total_assets=balance.get("total_assets"),
            total_liabilities=balance.get("total_liabilities"),
            total_debt=balance.get("total_debt"),
            cash_and_equivalents=balance.get("cash_and_equivalents"),
            net_ppe=balance.get("net_ppe"),
            retained_earnings=balance.get("retained_earnings"),
            stockholders_equity=balance.get("stockholders_equity"),
            current_assets=balance.get("current_assets"),
            current_liabilities=balance.get("current_liabilities"),
            # working_capital is not a stored XBRL concept; derive it from the
            # balance-sheet split so liquidity ratios (and the Graham current
            # ratio) work without a separate lookup.
            working_capital=(
                balance.get("current_assets") - balance.get("current_liabilities")
                if balance.get("current_assets") is not None
                and balance.get("current_liabilities") is not None
                else balance.get("working_capital")
            ),
            # Cash flow
            operating_cash_flow=cash_flow.get("operating_cash_flow"),
            capital_expenditure=cash_flow.get("capital_expenditure"),
            free_cash_flow=cash_flow.get("free_cash_flow"),
            depreciation_amortization=cash_flow.get("depreciation_amortization"),
            dividends_paid=cash_flow.get("dividends_paid"),
            repurchase_of_stock=cash_flow.get("repurchase_of_stock"),
            working_capital_change=cash_flow.get("working_capital_change"),
            # Additional income statement fields. These were historically dropped from
            # the snapshot because they only lived on an intermediate
            # IncomeStatement object that no caller consumed; carrying them
            # straight into the NormalizedFinancials makes e.g. R&D spent
            # visible to analytics and methodologies.
            operating_expense=income.get("operating_expense"),
            research_development=income.get("research_development"),
            sga=income.get("sga"),
            non_operating_income_expense=income.get("non_operating_income_expense"),
            preferred_dividends=income.get("preferred_dividends"),
            # Context
            shares_outstanding=balance.get("shares_outstanding"),
            split_adjustment_factor=split_adjustment_factor,
            sector=sector,
            period=ANNUAL_PERIOD,
            currency="USD",  # TODO: Get from actual unit/currency data
            source=ProviderName.EDGAR,  # Financial-DataBase primarily has SEC data
            loaded_at=loaded_at,
            # Data quality (we don't have this info directly, so use defaults)
            data_completeness=None,
            data_quality_score=None,
            is_complete=False,
            data_source_priority=1,  # SEC EDGAR is high quality
            derived_metrics=[],
        )

    # FinancialRepository interface implementation

    def upsert(self, financials: NormalizedFinancials) -> None:
        """Insert or update a single fiscal-year record.

        Note: This implementation is read-only for Financial-DataBase
        since we're primarily using it as a source of truth.
        For a full bidirectional sync, this would write to the database.
        """
        # Even though this is read-only, invalidate the ticker's cached
        # fundamentals so a future writer never serves stale data.
        self.invalidate_list_cache(financials.ticker.upper())

    def upsert_many(self, financials: list[NormalizedFinancials]) -> None:
        """Insert or update a batch of fiscal-year records in one operation."""
        # Read-only implementation; still invalidate the touched tickers.
        for row in financials:
            self.invalidate_list_cache(row.ticker.upper())

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

    # Core fields any usable fiscal year must populate. A reconstructed row
    # whose bucket picked up only stray non-income facts (e.g. an in-progress
    # year fed by an 8-K — NetFeeAmt/TtlFeeAmt/...) carries none of them and
    # is not a usable year: it must never be served as the latest available.
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
            getattr(row, field) is None
            for field in FinancialDatabaseRepository._EMPTY_ROW_FIELDS
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

    def delete_ticker(self, ticker: str) -> None:
        """Remove all records for a ticker.

        Read-only implementation - no-op for Financial-DataBase
        since we treat it as a source of truth.
        """

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

    # ------------------------------------------------------------------
    # per-year lookup cache (shares outstanding, fiscal-year-end)
    # ------------------------------------------------------------------
    def _lookup_cache(self):
        """The shared AnalysisCache, or None when no cache is wired in."""
        cache = getattr(self, "_analysis_cache", None)
        return cache if getattr(cache, "enabled", False) else None

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

    def __del__(self):
        """Cleanup connection on object destruction."""
        self.close()
