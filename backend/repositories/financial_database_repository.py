"""Financial Database repository: facade over the per-concern mixins.

This repository connects to the Financial-DataBase PostgreSQL database
and implements the FinancialRepository interface by querying the
normalized financial facts and reconstructing NormalizedFinancials
objects. The method groups live in ``backend/repositories/fdb_mixins/``
(facts, normalization, shares, fiscal year, filings, lookups); this
module keeps the connection/cache core and composes them.
"""

from __future__ import annotations

import os
import threading

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.value_objects.financials_normalized import NormalizedFinancials

# Compatibility: tests import these helpers from this module.
from backend.repositories.fdb_concept_mapping import _income_convention  # noqa: F401
from backend.repositories.fdb_mixins.facts_mixin import FactsMixin
from backend.repositories.fdb_mixins.filings_mixin import FilingsMixin
from backend.repositories.fdb_mixins.fiscal_year_mixin import FiscalYearMixin
from backend.repositories.fdb_mixins.helpers import (  # noqa: F401
    _as_date,
    _cumulative_split_multiplier,
)
from backend.repositories.fdb_mixins.lookups_mixin import LookupsMixin
from backend.repositories.fdb_mixins.normalization_mixin import NormalizationMixin
from backend.repositories.fdb_mixins.shares_mixin import SharesMixin


class FinancialDatabaseRepository(
    FactsMixin,
    NormalizationMixin,
    SharesMixin,
    FiscalYearMixin,
    FilingsMixin,
    LookupsMixin,
    FinancialRepository,
):
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

    def __del__(self):
        """Cleanup connection on object destruction."""
        self.close()
