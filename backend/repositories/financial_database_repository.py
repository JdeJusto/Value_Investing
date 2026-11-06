"""Financial Database repository: facade over the per-concern mixins.

This repository connects to the Financial-DataBase PostgreSQL database
and implements the FinancialRepository interface by querying the
normalized financial facts and reconstructing NormalizedFinancials
objects. The method groups live in ``backend/repositories/fdb_mixins/``
(facts, normalization, shares, fiscal year, filings, lookups); this
module keeps the connection/cache core and composes them.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import replace

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
    select_split_events,
)
from backend.repositories.fdb_mixins.lookups_mixin import LookupsMixin
from backend.repositories.fdb_mixins.normalization_mixin import NormalizationMixin
from backend.repositories.fdb_mixins.shares_mixin import SharesMixin

logger = logging.getLogger(__name__)

#: The eight canonical ``core_financials`` fields shown in the Evolution tab.
FIELDS_OF_INTEREST = (
    "revenue",
    "net_income",
    "operating_income",
    "gross_profit",
    "total_assets",
    "total_liabilities",
    "stockholders_equity",
    "cash",
)


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

    def available(self, *, retries: int = 0, retry_delay_s: float = 2.0) -> bool:
        """Check whether the Financial-DataBase answers a trivial query.

        ``retries`` extra attempts cover the window where PostgreSQL is still
        starting: the persistent systemd timer fires a couple of seconds after
        boot, before the database socket accepts connections. Failures are
        logged because a silent ``False`` used to send the daily run to the
        legacy JSON store, whose coverage is far lower.
        """
        attempts = max(1, int(retries) + 1)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                conn = self._get_connection()
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                return True
            except Exception as exc:  # noqa: BLE001 — DB drivers raise many types
                last_error = exc
                self._drop_connection()
                if attempt < attempts:
                    logger.warning(
                        "Financial-DataBase not ready (attempt %d/%d): %s; "
                        "retrying in %.1fs",
                        attempt,
                        attempts,
                        exc,
                        retry_delay_s,
                    )
                    time.sleep(retry_delay_s)
        logger.error(
            "Financial-DataBase unavailable after %d attempt(s): %s",
            attempts,
            last_error,
        )
        return False

    def _drop_connection(self) -> None:
        """Discard this thread's connection after a failed probe."""
        conn = getattr(self._local, "connection", None)
        self._local.connection = None
        if conn is None:
            return
        with self._connections_lock:
            self._connections.discard(conn)
        try:
            if not conn.closed:
                conn.close()
        except Exception:  # noqa: BLE001, S110 — best-effort teardown
            pass

    # ------------------------------------------------------------------
    # FDB 0.2.0 normalized layer
    # ------------------------------------------------------------------
    def get_effective_year(self, ticker: str) -> int | None:
        """Latest fiscal year with Assets and StockholdersEquity present.

        Liabilities may be absent (derived as Assets - Equity). MRX FY2025
        has Assets + Liabilities but no Equity, so it backs off to FY2024.
        """
        company_id = self._get_company_id_by_ticker(ticker)
        if not company_id:
            return None
        try:
            with self._get_connection().cursor() as cur:
                cur.execute(
                    """SELECT cf.fiscal_year
                       FROM core_financials cf
                       JOIN (
                         SELECT fiscal_year, MAX(period_end) AS period_end
                         FROM core_financials
                         WHERE company_id = %s
                         GROUP BY fiscal_year
                       ) latest
                         ON latest.fiscal_year = cf.fiscal_year
                        AND latest.period_end = cf.period_end
                       WHERE cf.company_id = %s
                         AND cf.total_assets IS NOT NULL
                         AND cf.stockholders_equity IS NOT NULL
                       ORDER BY cf.fiscal_year DESC
                       LIMIT 1""",
                    (company_id, company_id),
                )
                row = cur.fetchone()
            if row:
                value = row.get("fiscal_year") if hasattr(row, "get") else None
                if isinstance(value, int):
                    return value
        except (psycopg2.Error, KeyError, TypeError, ValueError):
            logger.debug(
                "core_financials unavailable; falling back to raw facts", exc_info=True
            )

        try:
            for item in self._list_years_uncached(ticker):
                if (
                    item.total_assets is not None
                    and item.stockholders_equity is not None
                ):
                    return item.fiscal_year
        except Exception:
            logger.debug("effective-year fallback failed for %s", ticker, exc_info=True)
        return None

    def get_core_financials(
        self, ticker: str, fiscal_year: int | None = None
    ) -> dict | None:
        """Read the eight canonical fields from FDB's ``core_financials`` MV.

        Returns the latest ``period_end`` for the requested year. When
        ``fiscal_year`` is None, resolves the effective year (latest year
        with Assets + StockholdersEquity) first. Also exposes the
        derived-liability fields from ``balance_effective``.
        """
        company_id = self._get_company_id_by_ticker(ticker)
        if not company_id:
            return None
        year = (
            fiscal_year if fiscal_year is not None else self.get_effective_year(ticker)
        )
        if year is None:
            return None
        sql = """SELECT cf.*, be.liabilities_effective, be.liabilities_derived
                 FROM core_financials cf
                 LEFT JOIN balance_effective be
                   ON be.company_id = cf.company_id
                  AND be.fiscal_year = cf.fiscal_year
                  AND be.period_end = cf.period_end
                 WHERE cf.company_id = %s AND cf.fiscal_year = %s
                 ORDER BY cf.period_end DESC LIMIT 1"""
        try:
            with self._get_connection().cursor() as cur:
                cur.execute(sql, [company_id, int(year)])
                row = cur.fetchone()
        except (psycopg2.Error, KeyError, TypeError, ValueError):
            logger.debug("core_financials read failed", exc_info=True)
            return None
        return dict(row) if row is not None and hasattr(row, "keys") else None

    def get_core_financials_batch(
        self, tickers: list[str], fiscal_year: int | None = None
    ) -> dict[str, dict]:
        """Batch version for screener/consensus/ranking (one SQL query).

        ``fiscal_year=None`` resolves each ticker's effective year in SQL
        (latest fiscal year with Assets + StockholdersEquity).
        """
        if not tickers:
            return {}
        if fiscal_year is None:
            sql = """WITH selected AS (
                         SELECT DISTINCT cl.company_id, cl.ticker
                         FROM company_listings cl
                         WHERE cl.ticker = ANY(%s) AND cl.is_active
                     ),
                     latest AS (
                         SELECT cf.company_id, cf.fiscal_year,
                                MAX(cf.period_end) AS period_end
                         FROM core_financials cf
                         JOIN selected s ON s.company_id = cf.company_id
                         GROUP BY cf.company_id, cf.fiscal_year
                     ),
                     effective AS (
                         SELECT DISTINCT ON (cf.company_id)
                                cf.company_id, cf.fiscal_year
                         FROM core_financials cf
                         JOIN latest l
                           ON l.company_id = cf.company_id
                          AND l.fiscal_year = cf.fiscal_year
                          AND l.period_end = cf.period_end
                         WHERE cf.total_assets IS NOT NULL
                           AND cf.stockholders_equity IS NOT NULL
                         ORDER BY cf.company_id, cf.fiscal_year DESC
                     )
                     SELECT DISTINCT ON (cl.ticker)
                            cl.ticker, cf.*, be.liabilities_effective,
                            be.liabilities_derived
                     FROM effective e
                     JOIN selected cl ON cl.company_id = e.company_id
                     JOIN core_financials cf
                       ON cf.company_id = e.company_id
                      AND cf.fiscal_year = e.fiscal_year
                     LEFT JOIN balance_effective be
                       ON be.company_id = cf.company_id
                      AND be.fiscal_year = cf.fiscal_year
                      AND be.period_end = cf.period_end
                     ORDER BY cl.ticker, cf.period_end DESC"""
            params: tuple = (list(tickers),)
        else:
            sql = """SELECT DISTINCT ON (cl.ticker)
                         cl.ticker, cf.*, be.liabilities_effective,
                         be.liabilities_derived
                     FROM core_financials cf
                     JOIN company_listings cl
                       ON cl.company_id = cf.company_id AND cl.is_active
                     LEFT JOIN balance_effective be
                       ON be.company_id = cf.company_id
                      AND be.fiscal_year = cf.fiscal_year
                      AND be.period_end = cf.period_end
                     WHERE cl.ticker = ANY(%s) AND cf.fiscal_year = %s
                     ORDER BY cl.ticker, cf.period_end DESC"""
            params = (list(tickers), int(fiscal_year))
        try:
            with self._get_connection().cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        except (psycopg2.Error, KeyError, TypeError, ValueError):
            logger.debug("core_financials batch read failed", exc_info=True)
            return {}
        return {
            row["ticker"]: dict(row)
            for row in rows
            if hasattr(row, "get") and row.get("ticker")
        }

    def get_financial_timeseries(
        self, ticker: str, years: int = 10
    ) -> dict[str, list[tuple[int, float | None]]]:
        """10-year evolution of the eight canonical ``core_financials`` fields.

        Rows are deduplicated per fiscal year by the latest ``period_end``.
        Missing fiscal years inside the requested window are returned as
        ``None`` (gaps), never invented. ``ticker`` may also be a company UUID
        for callers that already resolved it.
        """
        window = max(1, min(int(years), 20))
        company_id = self._get_company_id_by_ticker(str(ticker))
        if not company_id:
            company_id = str(ticker)
        empty = {field: [] for field in FIELDS_OF_INTEREST}
        sql = """SELECT fiscal_year, period_end, revenue, net_income,
                        operating_income, gross_profit, total_assets,
                        total_liabilities, stockholders_equity, cash
                 FROM core_financials
                 WHERE company_id = %s
                 ORDER BY fiscal_year DESC, period_end DESC"""
        try:
            with self._get_connection().cursor() as cur:
                cur.execute(sql, (company_id,))
                rows = cur.fetchall()
        except (psycopg2.Error, KeyError, TypeError, ValueError):
            logger.debug("core_financials timeseries read failed", exc_info=True)
            return empty
        if not rows:
            return empty

        by_year: dict[int, dict] = {}
        for row in rows:
            if not hasattr(row, "get"):
                continue
            try:
                year = int(row["fiscal_year"])
            except (KeyError, TypeError, ValueError):
                continue
            current = by_year.get(year)
            if current is None or str(row.get("period_end") or "") > str(
                current.get("period_end") or ""
            ):
                by_year[year] = row

        usable = [
            year
            for year, row in by_year.items()
            if any(row.get(field) is not None for field in FIELDS_OF_INTEREST)
        ]
        latest = max(usable) if usable else max(by_year)
        start = latest - window + 1
        series: dict[str, list[tuple[int, float | None]]] = {
            field: [] for field in FIELDS_OF_INTEREST
        }
        for year in range(start, latest + 1):
            row = by_year.get(year)
            for field in FIELDS_OF_INTEREST:
                value = row.get(field) if row is not None else None
                series[field].append(
                    (year, float(value) if value is not None else None)
                )
        return series

    def get_normalized_facts(
        self, ticker: str, fiscal_period: str = "FY"
    ) -> list[dict]:
        """Raw facts with FDB's normalized field/concept (read-only view)."""
        company_id = self._get_company_id_by_ticker(ticker)
        if not company_id:
            return []
        try:
            with self._get_connection().cursor() as cur:
                cur.execute(
                    """SELECT * FROM financial_facts_normalized
                       WHERE company_id = %s AND fiscal_period = %s
                       ORDER BY fiscal_year DESC, period_end DESC NULLS LAST""",
                    (company_id, fiscal_period.upper()),
                )
                rows = cur.fetchall()
        except (psycopg2.Error, KeyError, TypeError, ValueError):
            logger.debug("financial_facts_normalized unavailable", exc_info=True)
            return []
        return [dict(row) for row in rows if hasattr(row, "keys")]

    def get_balance_effective(self, ticker: str, fiscal_year: int) -> dict | None:
        """Derived-liability row for one fiscal year (latest period_end)."""
        company_id = self._get_company_id_by_ticker(ticker)
        if not company_id:
            return None
        try:
            with self._get_connection().cursor() as cur:
                cur.execute(
                    """SELECT * FROM balance_effective
                       WHERE company_id = %s AND fiscal_year = %s
                       ORDER BY period_end DESC LIMIT 1""",
                    (company_id, int(fiscal_year)),
                )
                row = cur.fetchone()
        except (psycopg2.Error, KeyError, TypeError, ValueError):
            logger.debug("balance_effective unavailable", exc_info=True)
            return None
        return dict(row) if row is not None and hasattr(row, "keys") else None

    def _core_rows_by_year(self, ticker: str) -> dict[int, dict]:
        company_id = self._get_company_id_by_ticker(ticker)
        if not company_id:
            return {}
        try:
            with self._get_connection().cursor() as cur:
                cur.execute(
                    """SELECT DISTINCT ON (fiscal_year) fiscal_year, *
                       FROM core_financials
                       WHERE company_id = %s
                       ORDER BY fiscal_year DESC, period_end DESC""",
                    (company_id,),
                )
                rows = cur.fetchall()
        except (psycopg2.Error, KeyError, TypeError, ValueError):
            return {}
        by_year: dict[int, dict] = {}
        for row in rows:
            if not hasattr(row, "get"):
                continue
            year = row.get("fiscal_year")
            if isinstance(year, int):
                by_year[year] = dict(row)
        return by_year

    @staticmethod
    def _merge_core_row(row, core: dict | None):
        if not core:
            return row
        updates = {}
        for field in (
            "revenue",
            "net_income",
            "operating_income",
            "gross_profit",
            "total_assets",
            "total_liabilities",
            "stockholders_equity",
        ):
            value = core.get(field)
            if value is not None:
                updates[field] = float(value)
        cash = core.get("cash")
        if cash is not None:
            updates["cash_and_equivalents"] = float(cash)
        if (
            updates.get("total_liabilities") is None
            and updates.get("total_assets") is not None
            and updates.get("stockholders_equity") is not None
        ):
            updates["total_liabilities"] = (
                updates["total_assets"] - updates["stockholders_equity"]
            )
        return replace(row, **updates) if updates else row

    def __del__(self):
        """Cleanup connection on object destruction."""
        self.close()
