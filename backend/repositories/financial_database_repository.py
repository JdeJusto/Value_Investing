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
from typing import Optional, List
from datetime import date, datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
    ANNUAL_PERIOD,
)
from backend.domain.entities.financials import (
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement,
)


def _period_end_year(value) -> Optional[int]:
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


# Concept mapping from Financial-DataBase XBRL concepts to Value Investing fields
# This maps common XBRL concepts to the financial statement fields we use
INCOME_STATEMENT_CONCEPTS = {
    # Revenue
    'Revenues': 'revenue',
    'Revenue': 'revenue',
    'RegulatedAndUnregulatedOperatingRevenue': 'revenue',
    'SalesRevenueNet': 'revenue',
    'RevenueFromContractWithCustomerExcludingAssessedTax': 'revenue',
    'RevenueFromContractWithCustomerIncludingAssessedTax': 'revenue',
    'SalesRevenueGoodsNet': 'revenue',
    'SalesRevenueServicesNet': 'revenue',
    # REITs file their rental income here when no 'Revenues' tag is present
    'OperatingLeaseLeaseIncome': 'revenue',

    # Cost of Goods Sold
    'CostOfGoodsSold': 'cogs',
    'CostOfRevenue': 'cogs',
    'CostOfGoodsAndServicesSold': 'cogs',

    # Gross Profit
    'GrossProfit': 'gross_profit',

    # Operating Expenses
    'OperatingExpenses': 'operating_expense',
    'ResearchAndDevelopmentExpense': 'research_development',
    'SellingGeneralAndAdministrativeExpense': 'sga',

    # Operating Income
    'OperatingIncomeLoss': 'operating_income',
    'OperatingIncome': 'operating_income',

    # EBIT (rarely reported separately; filers of OperatingIncomeLoss get a
    # matching ebit via the fallback in _normalize_financial_facts)
    'EBIT': 'ebit',

    # EBITDA
    'EBITDA': 'ebitda',

    # Non-operating Income/Expense
    'NonoperatingIncomeExpense': 'non_operating_income_expense',

    # Interest Expense
    'InterestExpense': 'interest_expense',

    # Tax Provision
    'IncomeTaxExpenseBenefit': 'tax_provision',
    'IncomeTaxExpense': 'tax_provision',

    # Pretax Income
    'IncomeLossBeforeIncomeTaxes': 'pretax_income',
    'PretaxIncome': 'pretax_income',

    # Net Income
    'NetIncomeLossAvailableToCommonStockholdersBasic': 'net_income',
    'NetIncomeLossAvailableToCommonStockholdersDiluted': 'net_income',
    'NetIncomeLoss': 'net_income',
    'NetIncome': 'net_income',
    'ProfitLoss': 'net_income',
}

# Some companies tag several elements with identical fiscal periods (e.g.
# RevenueFromContractWithCustomerExcludingAssessedTax for a single quarter vs
# Revenues for the full year, both with period_end=Dec-31). When several
# concepts map to the same field, prefer the most complete/representative one.
INCOME_FIELD_PRIORITY = {
    'revenue': [
        'Revenues',
        'Revenue',
        'RegulatedAndUnregulatedOperatingRevenue',
        'SalesRevenueNet',
        'SalesRevenueGoodsNet',
        'SalesRevenueServicesNet',
        'RevenueFromContractWithCustomerExcludingAssessedTax',
        'RevenueFromContractWithCustomerIncludingAssessedTax',
        # REIT rental income; ranked last so explicit revenue tags win, with a
        # value-based override in _normalize_financial_facts for REITs whose
        # rental income is the whole top line (e.g. CPT).
        'OperatingLeaseLeaseIncome',
    ],
    'net_income': [
        'NetIncomeLossAvailableToCommonStockholdersBasic',
        'NetIncomeLossAvailableToCommonStockholdersDiluted',
        'NetIncomeLoss',
        'NetIncome',
        'ProfitLoss',
    ],
}
INCOME_CONCEPT_RANK = {
    concept: rank
    for field, concepts in INCOME_FIELD_PRIORITY.items()
    for rank, concept in enumerate(concepts)
}

# Some companies file several capital-expenditure elements for the same period
# (e.g. AEP reports both PaymentsToAcquireProductiveAssets and the broader
# SegmentExpenditureAdditionToLongLivedAssets). Rank the concepts so the most
# complete figure wins instead of an arbitrary first-match.
CASH_FLOW_FIELD_PRIORITY = {
    'operating_cash_flow': [
        'NetCashProvidedByUsedInOperatingActivities',
        'OperatingCashFlow',
        # Filers with discontinued operations (e.g. JCI after divesting its
        # residential HVAC business) tag OCF only under the continuing-
        # operations variant; the plain tag is preferred when both exist.
        'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations',
    ],
    'capital_expenditure': [
        'PaymentsToAcquirePropertyPlantAndEquipment',
        'SegmentExpenditureAdditionToLongLivedAssets',
        'PaymentsToAcquireProductiveAssets',
        'PaymentsForConstructionInProcess',
        'CapitalExpenditures',
        'CapitalExpenditure',
    ],
    'depreciation_amortization': [
        'DepreciationDepletionAndAmortization',
        'DepreciationAndAmortization',
        # Variant add-back tags used by utilities (AEE: ...AccretionNet) and
        # capital-intensive filers (PWR: Depreciation).
        'DepreciationAmortizationAndAccretionNet',
        'Depreciation',
        # Single-line-item (non-add-back) tags ranked last; only chosen when no
        # complete add-back tag exists.
        'UtilitiesOperatingExpenseDepreciationAndAmortization',
        'CostOfGoodsSoldDepreciationDepletionAndAmortization',
    ],
}
CASH_FLOW_CONCEPT_RANK = {
    concept: rank
    for field, concepts in CASH_FLOW_FIELD_PRIORITY.items()
    for rank, concept in enumerate(concepts)
}

# Total debt = current + non-current portion, each taken from the newest
# balance comparative. Companies file several interchangeable tags for the
# same portion (LongTermDebt / DebtNoncurrent / LongTermDebtNoncurrent for
# non-current; DebtCurrent / ShortTermBorrowings / CommercialPaper for
# current), so ONE concept per portion is preferred by priority: summing
# every distinct tag would double count aliases (e.g. Newmont reports
# LongTermDebt and LongTermDebtNoncurrent with the same value, and D reports
# LongTermDebt plus the overlapping LongTermDebtAndCapitalLeaseObligations).
DEBT_CURRENT_PRIORITY = [
    'DebtCurrent',
    'ShortTermBorrowings',
    'CommercialPaper',
    'LongTermDebtAndCapitalLeaseObligationsCurrent',
    'LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities',
]
DEBT_NONCURRENT_PRIORITY = [
    'LongTermDebtAndCapitalLeaseObligations',
    'LongTermDebt',
    'DebtNoncurrent',
    'LongTermDebtNoncurrent',
    'LongTermNotesPayable',
    'SeniorNotes',
]
DEBT_CURRENT_RANK = {
    concept: rank
    for rank, concept in enumerate(DEBT_CURRENT_PRIORITY)
}
DEBT_NONCURRENT_RANK = {
    concept: rank
    for rank, concept in enumerate(DEBT_NONCURRENT_PRIORITY)
}

BALANCE_SHEET_CONCEPTS = {
    # Total Assets
    'Assets': 'total_assets',
    'AssetsTotal': 'total_assets',

    # Current Assets
    'AssetsCurrent': 'current_assets',
    'CashAndCashEquivalentsAtCarryingValue': 'cash_and_equivalents',
    'CashAndCashEquivalents': 'cash_and_equivalents',
    'AccountsReceivableNetCurrent': 'accounts_receivable',
    'InventoryNet': 'inventory',

    # Total Liabilities
    'Liabilities': 'total_liabilities',
    'LiabilitiesTotal': 'total_liabilities',

    # Current Liabilities
    'LiabilitiesCurrent': 'current_liabilities',
    'AccountsPayableCurrent': 'accounts_payable',

    # Long Term Liabilities
    'LongTermLiabilities': 'long_term_liabilities',

    # Total Debt (approximation)
    'DebtCurrent': 'total_debt',
    'DebtNoncurrent': 'total_debt',
    'LongTermDebt': 'total_debt',
    'LongTermDebtNoncurrent': 'total_debt',

    # Cash and Equivalents
    'CashAndCashEquivalentsAtCarryingValue': 'cash_and_equivalents',
    'CashAndCashEquivalents': 'cash_and_equivalents',
    # Asset managers/others that report only the restricted-inclusive total
    # (e.g. BEN: CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents)
    'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents': 'cash_and_equivalents',

    # Working Capital (calculated as Current Assets - Current Liabilities)
    # We'll calculate this separately since it's not typically stored directly

    # Retained Earnings
    'RetainedEarningsAccumulatedDeficit': 'retained_earnings',
    'RetainedEarnings': 'retained_earnings',

    # Stockholders Equity
    'StockholdersEquity': 'stockholders_equity',
    'TotalEquityGrossMinorityInterest': 'stockholders_equity',
    'ShareholdersEquity': 'stockholders_equity',

    # Shares Outstanding
    'WeightedAverageNumberOfSharesOutstandingBasic': 'shares_outstanding',
    'WeightedAverageNumberOfSharesOutstanding': 'shares_outstanding',
    'WeightedAverageNumberOfSharesOutstandingDiluted': 'shares_outstanding',
    # Point-in-time share counts (cover page / balance sheet). Financial-DataBase
    # stores these for most filers, and they are the only per-year share count
    # that survives when the weighted-average concepts are absent — without
    # them the P/E and P/BV criteria could never be evaluated.
    'CommonStockSharesOutstanding': 'shares_outstanding',
    'EntityCommonStockSharesOutstanding': 'shares_outstanding',
}

CASH_FLOW_CONCEPTS = {
    # Operating Cash Flow
    'NetCashProvidedByUsedInOperatingActivities': 'operating_cash_flow',
    'OperatingCashFlow': 'operating_cash_flow',
    # see CASH_FLOW_FIELD_PRIORITY['operating_cash_flow']
    'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations': 'operating_cash_flow',

    # Capital Expenditure (positive value)
    'PaymentsToAcquireProductiveAssets': 'capital_expenditure',
    'PaymentsToAcquirePropertyPlantAndEquipment': 'capital_expenditure',
    'SegmentExpenditureAdditionToLongLivedAssets': 'capital_expenditure',
    'PaymentsForConstructionInProcess': 'capital_expenditure',
    'CapitalExpenditures': 'capital_expenditure',
    'CapitalExpenditure': 'capital_expenditure',

    # Free Cash Flow (we'll calculate this as Operating CF - CapEx)

    # Depreciation and Amortization
    'DepreciationDepletionAndAmortization': 'depreciation_amortization',
    'DepreciationAndAmortization': 'depreciation_amortization',
    # Utilities/multi-entity filers use variant tags for the D&A add-back
    'DepreciationAmortizationAndAccretionNet': 'depreciation_amortization',
    'Depreciation': 'depreciation_amortization',
    'UtilitiesOperatingExpenseDepreciationAndAmortization': 'depreciation_amortization',
    'CostOfGoodsSoldDepreciationDepletionAndAmortization': 'depreciation_amortization',

    # Dividends Paid
    'PaymentsOfDividends': 'dividends_paid',
    'DividendsPaid': 'dividends_paid',

    # Repurchase of Stock
    'PaymentsForRepurchaseOfEquity': 'repurchase_of_stock',
    'RepurchaseOfCommonStock': 'repurchase_of_stock',

    # Working Capital Change (we'll calculate this)
}


CORE_STATEMENT_CONCEPTS = sorted(
    set(INCOME_STATEMENT_CONCEPTS)
    | set(BALANCE_SHEET_CONCEPTS)
    | set(CASH_FLOW_CONCEPTS)
)


class FinancialDatabaseRepository(FinancialRepository):
    """Repository that reads from Financial-DataBase PostgreSQL database.

    This repository queries the financial_facts table and reconstructs
    NormalizedFinancials objects by mapping XBRL concepts to financial
    statement fields.
    """

    def __init__(self, database_url: Optional[str] = None):
        """Initialize the repository with database connection.

        Args:
            database_url: PostgreSQL connection string. If None, uses
                         FINANCIAL_DATABASE_URL environment variable or
                         default to financial_database instance.
        """
        if database_url is None:
            database_url = os.environ.get(
                "FINANCIAL_DATABASE_URL",
                "postgresql://financial:test@localhost:5432/financial_database"
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

    def attach_analysis_cache(self, cache) -> "FinancialDatabaseRepository":
        """Wire the shared analysis cache (per-year lookups) and return self."""
        self._analysis_cache = cache
        return self

    # ------------------------------------------------------------------
    # per-run list_years cache helpers
    # ------------------------------------------------------------------
    def _list_cache_get(self, ticker: str) -> Optional[list[NormalizedFinancials]]:
        with self._list_cache_lock:
            return self._list_cache.get(ticker)

    def _list_cache_set(
        self, ticker: str, rows: list[NormalizedFinancials]
    ) -> None:
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
            except Exception:  # noqa: BLE001 — best-effort teardown
                pass
        self._local.connection = None

    def available(self) -> bool:
        """Check if the Financial-DataBase is available."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
        except Exception:
            return False

    def fundamentals_fingerprint(self, ticker: str) -> Optional[str]:
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
            for key in ("company_updated", "company_synced", "filing_count", "last_filing")
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def get_company_name(self, ticker: str) -> Optional[str]:
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
        except Exception:
            return None

    def has_active_listing(self, ticker: str) -> Optional[bool]:
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
                return False if cur.fetchone() is None else True
        except Exception:
            return None

    def get_cik(self, ticker: str) -> Optional[str]:
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
        except Exception:
            return None

    def _get_company_id_by_cik(self, cik: str) -> Optional[str]:
        """Get company ID from CIK.

        Args:
            cik: Central Index Key (10-digit string)

        Returns:
            Company UUID if found, None otherwise
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.id
                    FROM companies c
                    JOIN company_identifiers ci ON c.id = ci.company_id
                    JOIN data_providers dp ON ci.provider_id = dp.id
                    WHERE UPPER(ci.identifier_type) = 'CIK'
                      AND UPPER(ci.identifier_value) = %s
                      AND UPPER(dp.name) = 'SEC EDGAR'
                """, (cik.upper(),))
                result = cur.fetchone()
                return str(result['id']) if result else None
        except Exception:
            return None

    def _get_company_id_by_ticker(self, ticker: str) -> Optional[str]:
        """Get company ID from ticker symbol.

        Args:
            ticker: Company ticker symbol (e.g., 'AAPL')

        Returns:
            Company UUID if found, None otherwise
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.id
                    FROM companies c
                    JOIN company_identifiers ci ON c.id = ci.company_id
                    WHERE UPPER(ci.identifier_type) = 'TICKER'
                      AND UPPER(ci.identifier_value) = %s
                """, (ticker.upper(),))
                result = cur.fetchone()
                return str(result['id']) if result else None
        except Exception:
            return None

    def _get_listing_id_by_cik(self, cik: str) -> Optional[str]:
        """Get listing ID for a company's primary listing.

        Args:
            cik: Central Index Key (10-digit string)

        Returns:
            Listing UUID if found, None otherwise
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("""
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
                """, (cik.upper(),))
                result = cur.fetchone()
                return str(result['id']) if result else None
        except Exception:
            return None

    def _normalize_financial_facts(
        self, facts: List[dict], bucket_year: Optional[int] = None
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
            pe = f.get('period_end')
            ps = f.get('period_start')
            pe_ord = _date_ord(pe)
            ps_ord = _date_ord(ps)
            concept = f.get('concept') or ''
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
            (f.get('period_end') for f in facts
             if f.get('period_end') is not None
             and f.get('concept') in BALANCE_SHEET_CONCEPTS),
            None,
        )

        # Banks/brokers present a net-of-interest top line. Capture their
        # interest + non-interest income so their revenue can be reconstructed
        # when no net-revenue tag is filed.
        bank_interest = None
        bank_noninterest = None
        # REIT rental income (see the value-based override below).
        rental_income = None
        # Best current / non-current debt figure within the newest comparative
        # (concept-priority single pick per portion, see DEBT_*_PRIORITY).
        debt_current = None
        debt_noncurrent = None

        # Process each fact
        for fact in facts:
            concept = fact['concept']
            value = float(fact['value']) if fact['value'] is not None else None
            unit = fact['unit']
            fiscal_year = fact['fiscal_year']
            fiscal_period = fact['fiscal_period']

            # Skip if no value
            if value is None:
                continue

            # Map to income statement
            if concept in INCOME_STATEMENT_CONCEPTS:
                field_name = INCOME_STATEMENT_CONCEPTS[concept]
                if concept == 'OperatingLeaseLeaseIncome' and rental_income is None:
                    rental_income = value
                # Handle duplicates by taking the first fact ordered above
                if field_name not in income_data or income_data[field_name] is None:
                    income_data[field_name] = value

            # Map to balance sheet
            elif (
                concept in BALANCE_SHEET_CONCEPTS
                or concept in DEBT_CURRENT_RANK
                or concept in DEBT_NONCURRENT_RANK
            ):
                field_name = BALANCE_SHEET_CONCEPTS.get(concept, 'total_debt')
                # Total debt: take the current and non-current portions from the
                # SAME (newest) comparative, preferring one tag per portion so
                # equivalent aliases are not double counted.
                if field_name == 'total_debt':
                    if max_pe is not None and fact.get('period_end') != max_pe:
                        continue
                    cur_rank = DEBT_CURRENT_RANK.get(concept)
                    noncur_rank = DEBT_NONCURRENT_RANK.get(concept)
                    if cur_rank is not None:
                        if debt_current is None or cur_rank < debt_current[1]:
                            debt_current = (value, cur_rank)
                    elif noncur_rank is not None:
                        if debt_noncurrent is None or noncur_rank < debt_noncurrent[1]:
                            debt_noncurrent = (value, noncur_rank)
                else:
                    # Handle duplicates by taking the newest-comparative value
                    if field_name not in balance_data or balance_data[field_name] is None:
                        balance_data[field_name] = value

            # Map to cash flow
            elif concept in CASH_FLOW_CONCEPTS:
                field_name = CASH_FLOW_CONCEPTS[concept]
                # Handle capital expenditure (make positive)
                if field_name == 'capital_expenditure' and value is not None:
                    value = abs(value)  # Ensure positive

                # Handle duplicates by taking the newest-comparative value
                if field_name not in cash_flow_data or cash_flow_data[field_name] is None:
                    cash_flow_data[field_name] = value

            # Track bank top-line components (not part of the standard mapping)
            elif concept == 'InterestIncomeExpenseNet' and bank_interest is None:
                bank_interest = value
            elif concept == 'NoninterestIncome' and bank_noninterest is None:
                bank_noninterest = value
            elif concept == 'OperatingLeaseLeaseIncome' and rental_income is None:
                rental_income = value

        # Combine the current + non-current debt portions (single preferred tag
        # each) into total_debt. Absent both, the field stays unset.
        if debt_current is not None or debt_noncurrent is not None:
            balance_data['total_debt'] = (debt_current[0] if debt_current else 0.0) + (
                debt_noncurrent[0] if debt_noncurrent else 0.0
            )

        # Most filers present operating income (OperatingIncomeLoss) with no
        # separate EBIT tag; treat the two as equivalent so the EBIT-based
        # multiples (EV/EBIT, ROIC) keep working when only operating income is
        # filed.
        if (
            income_data.get('ebit') is None
            and income_data.get('operating_income') is not None
        ):
            income_data['ebit'] = income_data['operating_income']

        # REITs whose rental income is the whole top line (no revenue tag filed,
        # or only a small contract-revenue tag) report it as OperatingLease
        # LeaseIncome. Prefer the rental figure when it dominates whatever
        # contract-revenue tag was picked (e.g. CPT's 1.57B rental vs a 13M
        # contract tag) while leaving e.g. DD (6.85B sales vs 74M rental)
        # untouched. A non-positive rental figure never replaces a real top
        # line.
        if rental_income is not None and rental_income > 0 and (
            income_data.get('revenue') is None
            or rental_income > income_data['revenue']
        ):
            income_data['revenue'] = rental_income

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
            current_rev = income_data.get('revenue')
            if bank_total > 0 and (
                current_rev is None or bank_total > current_rev
            ):
                income_data['revenue'] = bank_total

        return {
            'income': income_data,
            'balance': balance_data,
            'cash_flow': cash_flow_data
        }

    def _calculate_derived_fields(self, statements: dict) -> dict:
        """Calculate derived fields like working capital and free cash flow.

        Args:
            statements: Dictionary with income, balance, cash_flow data

        Returns:
            Updated statements dictionary with derived fields calculated
        """
        balance = statements['balance']
        cash_flow = statements['cash_flow']

        # Calculate working capital: Current Assets - Current Liabilities
        # Since we don't have current assets/liabilities directly,
        # we'll approximate or skip for now
        # TODO: Add proper current assets/liabilities concept mapping

        # Calculate free cash flow: Operating Cash Flow - Capital Expenditure
        if (cash_flow.get('operating_cash_flow') is not None and
            cash_flow.get('capital_expenditure') is not None):
            cash_flow['free_cash_flow'] = (
                cash_flow['operating_cash_flow'] - cash_flow['capital_expenditure']
            )

        return statements

    def _build_normalized_financials(
        self,
        ticker: str,
        fiscal_year: int,
        statements: dict,
        loaded_at: Optional[datetime] = None
    ) -> NormalizedFinancials:
        """Build a NormalizedFinancials object from statement data.

        Args:
            ticker: Company ticker symbol
            fiscal_year: Fiscal year
            statements: Dictionary with income, balance, cash_flow data
            loaded_at: When this data was loaded (defaults to now)

        Returns:
            NormalizedFinancials object
        """
        if loaded_at is None:
            loaded_at = datetime.now(timezone.utc)

        income = statements['income']
        balance = statements['balance']
        cash_flow = statements['cash_flow']

        # Build IncomeStatement
        income_stmt = None
        if any(v is not None for v in income.values()):
            income_stmt = IncomeStatement(
                revenue=income.get('revenue'),
                cogs=income.get('cogs'),
                gross_profit=income.get('gross_profit'),
                operating_income=income.get('operating_income'),
                ebit=income.get('ebit'),
                ebitda=income.get('ebitda'),
                net_income=income.get('net_income'),
                interest_expense=income.get('interest_expense'),
                tax_provision=income.get('tax_provision'),
                pretax_income=income.get('pretax_income'),
                operating_expense=income.get('operating_expense'),
                research_development=income.get('research_development'),
                sga=income.get('sga'),
                non_operating_income_expense=income.get('non_operating_income_expense')
            )

        # Build BalanceSheet
        balance_stmt = None
        if any(v is not None for v in balance.values()):
            balance_stmt = BalanceSheet(
                total_assets=balance.get('total_assets'),
                total_liabilities=balance.get('total_liabilities'),
                total_debt=balance.get('total_debt'),
                cash_and_equivalents=balance.get('cash_and_equivalents'),
                retained_earnings=balance.get('retained_earnings'),
                stockholders_equity=balance.get('stockholders_equity')
            )

        # Build CashFlowStatement
        cash_flow_stmt = None
        if any(v is not None for v in cash_flow.values()):
            cash_flow_stmt = CashFlowStatement(
                operating_cash_flow=cash_flow.get('operating_cash_flow'),
                capital_expenditure=cash_flow.get('capital_expenditure'),
                free_cash_flow=cash_flow.get('free_cash_flow'),
                depreciation_amortization=cash_flow.get('depreciation_amortization'),
                dividends_paid=cash_flow.get('dividends_paid'),
                repurchase_of_stock=cash_flow.get('repurchase_of_stock'),
                working_capital_change=cash_flow.get('working_capital_change')
            )

        return NormalizedFinancials(
            ticker=ticker,
            fiscal_year=fiscal_year,
            # Income statement
            revenue=income.get('revenue'),
            cogs=income.get('cogs'),
            gross_profit=income.get('gross_profit'),
            operating_income=income.get('operating_income'),
            ebit=income.get('ebit'),
            ebitda=income.get('ebitda'),
            net_income=income.get('net_income'),
            interest_expense=income.get('interest_expense'),
            tax_provision=income.get('tax_provision'),
            pretax_income=income.get('pretax_income'),
            # Balance sheet
            total_assets=balance.get('total_assets'),
            total_liabilities=balance.get('total_liabilities'),
            total_debt=balance.get('total_debt'),
            cash_and_equivalents=balance.get('cash_and_equivalents'),
            retained_earnings=balance.get('retained_earnings'),
            stockholders_equity=balance.get('stockholders_equity'),
            current_assets=balance.get('current_assets'),
            current_liabilities=balance.get('current_liabilities'),
            # working_capital is not a stored XBRL concept; derive it from the
            # balance-sheet split so liquidity ratios (and the Graham current
            # ratio) work without a separate lookup.
            working_capital=(
                balance.get('current_assets') - balance.get('current_liabilities')
                if balance.get('current_assets') is not None
                and balance.get('current_liabilities') is not None
                else balance.get('working_capital')
            ),
            # Cash flow
            operating_cash_flow=cash_flow.get('operating_cash_flow'),
            capital_expenditure=cash_flow.get('capital_expenditure'),
            free_cash_flow=cash_flow.get('free_cash_flow'),
            depreciation_amortization=cash_flow.get('depreciation_amortization'),
            dividends_paid=cash_flow.get('dividends_paid'),
            repurchase_of_stock=cash_flow.get('repurchase_of_stock'),
            working_capital_change=cash_flow.get('working_capital_change'),
            # Context
            shares_outstanding=balance.get('shares_outstanding'),
            period=ANNUAL_PERIOD,
            currency='USD',  # TODO: Get from actual unit/currency data
            source=ProviderName.EDGAR,  # Financial-DataBase primarily has SEC data
            loaded_at=loaded_at,
            # Data quality (we don't have this info directly, so use defaults)
            data_completeness=None,
            data_quality_score=None,
            is_complete=False,
            data_source_priority=1,  # SEC EDGAR is high quality
            derived_metrics=[]
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

    def upsert_many(self, financials: List[NormalizedFinancials]) -> None:
        """Insert or update a batch of fiscal-year records in one operation."""
        # Read-only implementation; still invalidate the touched tickers.
        for row in financials:
            self.invalidate_list_cache(row.ticker.upper())

    def get_by_year(
        self, ticker: str, fiscal_year: int
    ) -> Optional[NormalizedFinancials]:
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
                cur.execute("""
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
                """, (company_id, fiscal_year))

                facts = cur.fetchall()

                if not facts:
                    return None

                # Normalize the facts
                statements = self._normalize_financial_facts(
                    facts, bucket_year=fiscal_year
                )
                statements = self._calculate_derived_fields(statements)

                # Build and return NormalizedFinancials
                return self._build_normalized_financials(
                    ticker=ticker.upper(),
                    fiscal_year=fiscal_year,
                    statements=statements
                )

        except Exception:
            # In case of any error, return None to let fallback handle it
            return None

    def list_years(self, ticker: str) -> List[NormalizedFinancials]:
        """Return the best record per year for a ticker, most recent first.

        Results are cached for the lifetime of this repository instance so the
        two calls ``analyze`` makes per ticker (``_load_history`` and
        ``_data_reliability``) re-use one query + normalization instead of
        fetching the full FY history twice. Only non-empty results are cached
        and ``invalidate_list_cache``/``upsert*`` clear a ticker when its data
        changes, so a deliberate refresh never serves stale fundamentals.
        """
        ticker = ticker.upper()
        cached = self._list_cache_get(ticker)
        if cached is not None:
            return list(cached)

        rows = self._list_years_uncached(ticker)

        if rows:
            self._list_cache_set(ticker, rows)
        else:
            # Negative lookups are never cached: a loader/sync may populate the
            # company in between and the next read must see the fresh data.
            self.invalidate_list_cache(ticker)
        return rows

    def _list_years_uncached(self, ticker: str) -> List[NormalizedFinancials]:
        """The uncached list_years implementation (see ``list_years``).

        All *annual* (FY) facts for the company are fetched in a single query
        and bucketed by fiscal year, replacing the old per-year ``get_by_year``
        round-trips (3 + 2×N queries per ticker) with 2 queries. The rows fed
        to ``_normalize_financial_facts`` per year are identical to what
        ``get_by_year`` produced, so the reconstructed records do not change.
        """
        try:
            # Get company ID from ticker (same as get_by_year)
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return []

            conn = self._get_connection()
            facts = []
            with conn.cursor() as cur:
                # Only annual ('FY') facts are used: the fiscal_year bucket also
                # holds quarterly YTD facts and the comparative years embedded in
                # the latest 10-K, so filtering to 'FY' is what makes each value
                # represent a completed fiscal year (see _normalize_financial_facts
                # for the max-period_end dedup).
                cur.execute("""
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
                """, (company_id,))
                facts = cur.fetchall()

            if not facts:
                return []

            by_year: dict[int, list] = {}
            for row in facts:
                by_year.setdefault(row["fiscal_year"], []).append(row)

            results: List[NormalizedFinancials] = []
            for year in sorted(by_year, reverse=True):
                try:
                    statements = self._normalize_financial_facts(
                        by_year[year], bucket_year=year
                    )
                    statements = self._calculate_derived_fields(statements)
                    financials = self._build_normalized_financials(
                        ticker=ticker.upper(),
                        fiscal_year=year,
                        statements=statements,
                    )
                    if financials is not None:
                        results.append(financials)
                except Exception:  # noqa: BLE001 — one bad year must not drop the rest
                    continue
            return results

        except Exception:
            return []

    def list_all(self, ticker: str) -> List[NormalizedFinancials]:
        """Return every stored record (all sources), year desc."""
        # For Financial-DataBase, we primarily have SEC EDGAR data
        # and we don't have multiple sources, so we return the same as list_years.
        return self.list_years(ticker)

    def get_best_available(self, ticker: str) -> List[NormalizedFinancials]:
        """Return the most consistent usable history for a ticker.

        For Financial-DataBase, we assume SEC EDGAR data is consistently
        high quality, so we just return all available years.
        """
        return self.list_all(ticker)

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
                cur.execute("""
                    SELECT ci.identifier_value as cik
                    FROM company_identifiers ci
                    WHERE ci.company_id = %s
                      AND ci.identifier_type = 'CIK'
                      AND ci.provider_id = (SELECT id FROM data_providers WHERE name = 'SEC EDGAR')
                """, (company_id,))

                cik_result = cur.fetchone()
                if not cik_result:
                    return False

                cik = cik_result['cik']

                # Check if there's any financial data for this company
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM financial_facts f
                    WHERE f.company_id = %s
                """, (company_id,))

                result = cur.fetchone()
                return result['count'] > 0 if result else False

        except Exception:
            return False

    def delete_ticker(self, ticker: str) -> None:
        """Remove all records for a ticker.

        Read-only implementation - no-op for Financial-DataBase
        since we treat it as a source of truth.
        """
        pass

    def get_normalized_financials(self, ticker: str, fiscal_year: int) -> Optional[NormalizedFinancials]:
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
    ) -> Optional[float]:
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
    ) -> Optional[float]:
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
            'CommonStockSharesOutstanding',
            'WeightedAverageNumberOfSharesOutstandingBasic',
            'WeightedAverageNumberOfSharesOutstanding',
            'WeightedAverageNumberOfSharesOutstandingDiluted',
            'WeightedAverageNumberOfDilutedSharesOutstanding',
        ]
        diluted = [
            'WeightedAverageNumberOfSharesOutstandingDiluted',
            'WeightedAverageNumberOfDilutedSharesOutstanding',
            'CommonStockSharesOutstanding',
            'WeightedAverageNumberOfSharesOutstandingBasic',
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
                    cur.execute("""
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
                    """, (company_id, fiscal_year, concept))

                    rows = cur.fetchall()
                    candidate = _pick(
                        [r['value'] for r in rows if r['value'] is not None],
                        [r['period_end'] for r in rows if r['value'] is not None],
                    ) if rows else None
                    if candidate is not None:
                        break

                # Fallback: no annual fact — accept any period (rare)
                if candidate is None:
                    for concept in concepts_to_try:
                        cur.execute("""
                            SELECT f.value, f.filing_date, f.period_end
                            FROM financial_facts f
                            WHERE f.company_id = %s
                              AND f.fiscal_year = %s
                              AND f.concept = %s
                            ORDER BY (f.period_end - COALESCE(f.period_start, f.period_end)) DESC,
                                     f.filing_date ASC NULLS LAST
                            LIMIT 2
                        """, (company_id, fiscal_year, concept))

                        rows = cur.fetchall()
                        candidate = _pick(
                            [r['value'] for r in rows if r['value'] is not None],
                            [r['period_end'] for r in rows if r['value'] is not None],
                        ) if rows else None
                        if candidate is not None:
                            break

                # Legacy SEC filings (pre-2011) sometimes tag weighted-average
                # share counts in thousands while the cover-page share count is
                # correct (e.g. Ball Corp 2010 weighted-average basic = 180,746
                # but outstanding stood at 169,198,602). Detect the scale
                # mismatch against EntityCommonStockSharesOutstanding and repair
                # the candidate so per-share metrics are not inflated ~1000x.
                if candidate is not None and candidate > 0:
                    cur.execute("""
                        SELECT f.value
                        FROM financial_facts f
                        WHERE f.company_id = %s
                          AND f.fiscal_year = %s
                          AND f.concept = 'EntityCommonStockSharesOutstanding'
                          AND UPPER(f.fiscal_period) = 'FY'
                        ORDER BY f.period_end DESC NULLS LAST
                        LIMIT 1
                    """, (company_id, fiscal_year))

                    result = cur.fetchone()
                    anchor = (
                        float(result['value'])
                        if result and result['value'] is not None
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

        except Exception:
            return None

    def get_available_to_common_diluted_net_income(
        self, ticker: str, fiscal_year: int
    ) -> Optional[float]:
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
                cur.execute("""
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
                """, (company_id, fiscal_year, fiscal_year))

                result = cur.fetchone()
                if result and result['value'] is not None:
                    return float(result['value'])
                return None

        except Exception:
            return None

    def get_fiscal_year_end_date(self, ticker: str, fiscal_year: int) -> Optional[date]:
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
    ) -> Optional[date]:
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
                cur.execute("""
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
                """, (company_id, fiscal_year,
                      CORE_STATEMENT_CONCEPTS, fiscal_year))

                result = cur.fetchone()
                if result and result['period_end'] is not None:
                    period_end = result['period_end']
                    if isinstance(period_end, date):
                        return period_end
                    return date.fromisoformat(str(period_end)[:10])
                return None

        except Exception:
            return None

    def get_latest_completed_fiscal_year(self, ticker: str) -> Optional[int]:
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
                cur.execute("""
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
                """, (company_id,))

                result = cur.fetchone()
                if result and result['fiscal_year'] is not None:
                    return int(result['fiscal_year'])
                return None

        except Exception:
            return None

    def __del__(self):
        """Cleanup connection on object destruction."""
        self.close()