"""On-demand SEC refresh + real-time price service.

Ensures that the tickers being analyzed have fresh fundamentals in
Financial-DataBase — via a targeted per-CIK ``sec sync <CIK>`` for each
company whose data is stale (never a blanket full-universe sync) — and
returns current prices fetched from Yahoo Finance on demand.

Prices are NEVER persisted anywhere: they come from the in-memory
PriceService cache and are returned in ``RefreshResult.prices`` for the
caller to display; nothing is written to any database.

Degradation contract
--------------------
- If Financial-DataBase is unreachable, refresh is skipped with a clear
  ``failed`` entry but the command still runs (prices may still be fetched).
- If ``SEC_USER_AGENT`` is not set, the targeted sync is reported as failed
  with that reason instead of crashing the whole command.
- Before any sync, a SEC availability preflight (``sec_health.py``) turns a
  403 rate-limit / unreachable EDGAR into a single skip: the companies move
  to ``RefreshResult.skipped`` and ``sec_skipped_reason`` records why,
  instead of one doomed ``sec sync`` subprocess per company. Analysis
  proceeds with the stored fundamentals.
- If SEC is unreachable or the sync times out mid-run, the company is
  reported as failed and analysis proceeds with the data that exists.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from backend.services.price_service import PriceService
from backend.services.sec_health import SecHealth, check_sec_availability

logger = logging.getLogger("backend.refresh_service")

# Defaults for config/refresh.yaml (the file itself is optional and only
# overrides these).
DEFAULT_AUTO_REFRESH = True
DEFAULT_FRESHNESS_MAX_AGE_HOURS = 168  # 7 days
DEFAULT_REFRESH_TIMEOUT_SECONDS = 300
DEFAULT_SKIP_REFRESH_FLAG = False
# Concurrent targeted ``sec sync`` subprocesses. 2 halves the refresh wall
# time vs sequential while keeping the SEC request burst small (each sync is
# a handful of requests; the scheduler still applies its own pacing).
DEFAULT_REFRESH_WORKERS = 2
# Consecutive 429/401 price failures before the stage gives up (0 = never).
DEFAULT_PRICE_ABORT_AFTER = 3

# Well-known location of the Financial-DataBase checkout, overridable with
# FINANCIAL_DATABASE_REPO_PATH. The FDB project lives as a sibling of this
# repository (e.g. ~/Financial-DataBase next to ~/Value_Investing).
_VI_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_FDB_REPO = os.path.join(os.path.dirname(_VI_ROOT), "Financial-DataBase")


@dataclass
class RefreshConfig:
    """Behavior of the on-demand refresh step, from config/refresh.yaml."""

    auto_refresh: bool = DEFAULT_AUTO_REFRESH
    freshness_max_age_hours: int = DEFAULT_FRESHNESS_MAX_AGE_HOURS
    refresh_timeout_seconds: int = DEFAULT_REFRESH_TIMEOUT_SECONDS
    skip_refresh_flag: bool = DEFAULT_SKIP_REFRESH_FLAG
    refresh_workers: int = DEFAULT_REFRESH_WORKERS
    # Consecutive non-transient Yahoo failures (429/401) that abort the price
    # stage; 0 disables the abort. From config/refresh.yaml.
    price_abort_after_consecutive_non_transient: int = DEFAULT_PRICE_ABORT_AFTER


@dataclass
class RefreshResult:
    """Outcome of ensure_fresh_and_prices for one batch of tickers."""

    refreshed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    prices: dict[str, float | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # Set when the SEC preflight declared EDGAR unavailable and the whole
    # targeted sync step was skipped (companies move to ``skipped``). The
    # reason is the human-readable probe outcome.
    sec_skipped_reason: str | None = None

    @property
    def ok(self) -> bool:
        return not self.failed


class FdbGateway:
    """Read-only access to Financial-DataBase (companies, freshness).

    Only reads metadata and ingestion timestamps; never writes. Prices are
    not part of this gateway — they flow through PriceService.
    """

    def __init__(self, database_url: str | None = None):
        if database_url is None:
            database_url = os.environ.get(
                "FINANCIAL_DATABASE_URL",
                "postgresql://financial:test@localhost:5432/financial_database",
            )
        self.database_url = database_url
        self._conn = None

    # ------------------------------------------------------------------
    def _connection(self):
        import psycopg2
        from psycopg2.extras import RealDictCursor

        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
        return self._conn

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
        self._conn = None

    def available(self) -> bool:
        try:
            with self._connection().cursor() as cur:
                cur.execute("SELECT 1")
                return True
        except Exception:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
            return False

    def staleness_bulk(
        self, tickers: list[str]
    ) -> dict[str, tuple[str | None, str | None, _dt.datetime | None]]:
        """Resolve (company_id, CIK, last ingestion timestamp) for many tickers.

        The whole scan runs in two queries instead of two round-trips per
        ticker (the sequential resolve_company/last_synced_at path), with the
        same semantics. Returns ``{ticker: (company_id, cik, last)}``;
        company_id/cik are None when the ticker has no listing or CIK, and
        ``last`` is None when the company has no ingestion timestamps.
        """
        lookup: list[str] = []
        seen: set[str] = set()
        for ticker in tickers or []:
            t = str(ticker).strip().upper()
            if t and t not in seen:
                seen.add(t)
                lookup.append(t)
        out: dict[str, tuple[str | None, str | None, _dt.datetime | None]] = {
            t: (None, None, None) for t in lookup
        }
        if not lookup:
            return out
        cur = self._connection().cursor()
        try:
            cur.execute(
                """
                SELECT upper(cl.ticker) AS ticker, c.id::text AS company_id,
                       ci.identifier_value AS cik
                FROM company_listings cl
                JOIN companies c ON c.id = cl.company_id
                JOIN company_identifiers ci
                  ON ci.company_id = c.id AND ci.identifier_type = 'CIK'
                WHERE upper(cl.ticker) = ANY(%s)
                ORDER BY cl.is_active DESC, ci.identifier_value
                """,
                (lookup,),
            )
            for row in cur.fetchall():
                t = str(row["ticker"]).upper()
                if t in out and out[t][0] is None:
                    out[t] = (str(row["company_id"]), str(row["cik"]), None)
            ids = [v[0] for v in out.values() if v[0] is not None]
            if ids:
                cur.execute(
                    """
                    SELECT c.id::text AS company_id, GREATEST(
                        (SELECT max(updated_at) FROM financial_facts
                          WHERE company_id = c.id),
                        (SELECT max(created_at) FROM filings
                          WHERE company_id = c.id),
                        (SELECT updated_at FROM companies WHERE id = c.id),
                        -- Newest successful per-company import run (SEC sync /
                        -- submissions / companyfacts record company_id since
                        -- migration 0021). GREATEST ignores NULLs, so for
                        -- companies without a scoped run this term simply
                        -- falls back to the timestamp expression above.
                        (SELECT max(ir.finished_at) FROM import_runs ir
                          WHERE ir.company_id = c.id AND ir.status = 'success')
                    ) AS last_ingested
                    FROM companies c
                    WHERE c.id = ANY(%s::uuid[])
                    """,
                    (ids,),
                )
                by_id = {
                    str(row["company_id"]): row["last_ingested"]
                    for row in cur.fetchall()
                }
                for ticker, (cid, cik, _) in out.items():
                    if cid in by_id and by_id[cid] is not None:
                        out[ticker] = (cid, cik, by_id[cid])
        finally:
            cur.close()
        return out

    # ------------------------------------------------------------------
    def resolve_company(self, ticker: str) -> tuple[str, str] | None:
        """Return (company_id, CIK) for a ticker, preferring active listings.

        Returns None when the ticker has no listing or no CIK identifier.
        """
        try:
            with self._connection().cursor() as cur:
                cur.execute(
                    """
                    SELECT c.id AS company_id, ci.identifier_value AS cik
                    FROM company_listings cl
                    JOIN companies c ON c.id = cl.company_id
                    JOIN company_identifiers ci
                      ON ci.company_id = c.id
                     AND ci.identifier_type = 'CIK'
                    WHERE upper(cl.ticker) = upper(%s)
                    ORDER BY cl.is_active DESC, ci.identifier_value
                    LIMIT 1
                    """,
                    (ticker,),
                )
                row = cur.fetchone()
        except Exception:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
            return None
        if not row:
            return None
        return str(row["company_id"]), str(row["cik"])

    def stale_companies(
        self,
        *,
        max_age_hours: int | None = None,
        limit: int = 500,
        priority: str = "recent_filings",
    ) -> list[dict]:
        """Companies with an active listing whose fundamentals are stale.

        Unlike :meth:`staleness_bulk` this is *company* scoped and needs no
        universe file: it is what a catch-up of out-of-universe names needs
        (Russell 2000 companies that never reached ``config/universe.csv``,
        OTC/foreign listings, delisted issuers). One read-only query, ordered
        by ``priority``:

        - ``recent_filings`` (default) — the companies whose newest filing is
          most recent first, i.e. those with the most to gain;
        - ``alphabetical`` — deterministic and easy to eyeball;
        - ``random`` — spread the load without a systematic bias.

        ``limit`` bounds the result so a catch-up can never turn into a
        whole-database sync by accident. Companies that were never ingested
        sort last for ``recent_filings`` (no filing date to compare).
        """
        if priority not in ("recent_filings", "alphabetical", "random"):
            raise ValueError(
                f"unknown priority {priority!r}: use recent_filings, "
                "alphabetical or random"
            )
        hours = 168 if max_age_hours is None else int(max_age_hours)
        order = {
            "recent_filings": "last_filing DESC NULLS LAST, c.legal_name",
            "alphabetical": "c.legal_name",
            "random": "random()",
        }[priority]
        sql = f"""
            SELECT c.id::text AS company_id,
                   ci.identifier_value AS cik,
                   c.legal_name,
                   c.last_synced_at,
                   (SELECT max(f.created_at) FROM filings f
                     WHERE f.company_id = c.id) AS last_filing,
                   (SELECT count(*) FROM filings f
                     WHERE f.company_id = c.id) AS filing_count
            FROM companies c
            JOIN company_identifiers ci
              ON ci.company_id = c.id
             AND UPPER(ci.identifier_type) = 'CIK'
            WHERE (c.last_synced_at IS NULL
                   OR c.last_synced_at < NOW() - (%s || ' hours')::interval)
              AND EXISTS (
                  SELECT 1 FROM company_listings cl
                  WHERE cl.company_id = c.id AND cl.is_active
              )
            ORDER BY {order}
            LIMIT %s
        """
        try:
            with self._connection().cursor() as cur:
                cur.execute(sql, (str(hours), int(limit)))
                rows = cur.fetchall() or []
        except Exception as exc:  # noqa: BLE001 — a gateway query never crashes a run
            logger.warning("stale_companies: query failed: %s", exc)
            return []
        return [dict(row) for row in rows]

    def last_synced_at(self, company_id: str) -> _dt.datetime | None:
        """Last ingestion timestamp for a company, from data timestamps.

        import_runs has no per-CIK scope, so freshness is derived from the
        most recent fact/filing write OR the companies row — the companies
        row is touched (updated_at) on every successful sec sync, which is
        what makes a just-refreshed company look fresh on the next run even
        when SEC reported no changes.
        """
        try:
            with self._connection().cursor() as cur:
                cur.execute(
                    """
                    SELECT GREATEST(
                        (SELECT max(updated_at) FROM financial_facts WHERE company_id = %s),
                        (SELECT max(created_at) FROM filings WHERE company_id = %s),
                        (SELECT updated_at FROM companies WHERE id = %s)
                    ) AS last_ingested
                    """,
                    (company_id, company_id, company_id),
                )
                row = cur.fetchone()
        except Exception:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
            return None
        if not row or row["last_ingested"] is None:
            return None
        value = row["last_ingested"]
        if isinstance(value, _dt.datetime):
            return value
        return _dt.datetime.fromisoformat(str(value))


def load_refresh_config(path: str | None = None) -> RefreshConfig:
    """Load config/refresh.yaml into a RefreshConfig.

    The YAML file is intentionally tiny (flat ``key: value`` pairs), so it
    is parsed without a YAML dependency. Missing file or keys fall back to
    the defaults; environment variables win over the file:
      REFRESH_AUTO, FRESHNESS_MAX_AGE_HOURS, REFRESH_TIMEOUT_SECONDS,
      REFRESH_SKIP_FLAG, REFRESH_WORKERS
    """
    config = RefreshConfig()

    # Config file (optional overlay).
    if path is None:
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "config",
            "refresh.yml",
        )
        # Prefer refresh.yaml; tolerate either extension.
        yaml_path = os.path.join(os.path.dirname(path), "refresh.yaml")
        if os.path.exists(yaml_path):
            path = yaml_path

    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.split("#", 1)[0].strip()
                if not line or ":" not in line:
                    continue
                key, _, raw = line.partition(":")
                key = key.strip().lower()
                raw = raw.strip()
                if key == "auto_refresh":
                    config.auto_refresh = raw.lower() in ("true", "1", "yes")
                elif key == "freshness_max_age_hours":
                    try:
                        config.freshness_max_age_hours = int(raw)
                    except ValueError:
                        pass
                elif key == "refresh_timeout_seconds":
                    try:
                        config.refresh_timeout_seconds = int(raw)
                    except ValueError:
                        pass
                elif key == "skip_refresh_flag":
                    config.skip_refresh_flag = raw.lower() in ("true", "1", "yes")
                elif key == "refresh_workers":
                    try:
                        config.refresh_workers = max(1, int(raw))
                    except ValueError:
                        pass
                elif key == "price_abort_after_consecutive_non_transient":
                    try:
                        config.price_abort_after_consecutive_non_transient = max(
                            0, int(raw)
                        )
                    except ValueError:
                        pass

    # Environment overrides.
    env = os.environ
    if env.get("REFRESH_AUTO", "").strip():
        config.auto_refresh = env["REFRESH_AUTO"].strip().lower() in ("true", "1", "yes")
    if env.get("FRESHNESS_MAX_AGE_HOURS", "").strip():
        try:
            config.freshness_max_age_hours = int(env["FRESHNESS_MAX_AGE_HOURS"])
        except ValueError:
            pass
    if env.get("REFRESH_TIMEOUT_SECONDS", "").strip():
        try:
            config.refresh_timeout_seconds = int(env["REFRESH_TIMEOUT_SECONDS"])
        except ValueError:
            pass
    if env.get("REFRESH_SKIP_FLAG", "").strip():
        config.skip_refresh_flag = (
            env["REFRESH_SKIP_FLAG"].strip().lower() in ("true", "1", "yes")
        )
    if env.get("REFRESH_WORKERS", "").strip():
        try:
            config.refresh_workers = max(1, int(env["REFRESH_WORKERS"]))
        except ValueError:
            pass
    if env.get("PRICE_ABORT_AFTER", "").strip():
        try:
            config.price_abort_after_consecutive_non_transient = max(
                0, int(env["PRICE_ABORT_AFTER"])
            )
        except ValueError:
            pass

    return config


@dataclass
class DCFConfig:
    """Toggles for the supplementary ``not-from-canon`` DCF sections.

    The DCF module (``backend/valuation/``) sits outside the five book
    methodologies by design; these flags only control where its supplementary
    sections appear (analyze-full, daily report) — never any scoring.
    """

    in_analyze_full: bool = True
    in_daily_report: bool = True
    daily_report_top_n: int = 10


def load_dcf_config(path: str | None = None) -> DCFConfig:
    """Load the ``dcf:`` block of config/refresh.yaml (optional overlay).

    Parsed with the same dependency-free line parser as refresh.yaml: the
    file is optional and missing keys fall back to the defaults. Environment
    overrides: ``DCF_IN_ANALYZE_FULL``, ``DCF_IN_DAILY_REPORT`` and
    ``DCF_DAILY_REPORT_TOP_N``.
    """
    config = DCFConfig()
    if path is None:
        base = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "config",
        )
        path = os.path.join(base, "refresh.yaml")
        if not os.path.exists(path):
            path = os.path.join(base, "refresh.yml")
    if path and os.path.exists(path):
        in_dcf = False
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                raw_line = line.rstrip("\n")
                stripped = raw_line.strip()
                if stripped == "dcf:":
                    in_dcf = True
                    continue
                if in_dcf and stripped and not raw_line[:1].isspace():
                    # A sibling top-level key ends the dcf block.
                    in_dcf = False
                if not in_dcf:
                    continue
                body = stripped.split("#", 1)[0].strip()
                if not body or ":" not in body:
                    continue
                key, _, value = body.partition(":")
                key, value = key.strip().lower(), value.strip()
                if key == "in_analyze_full":
                    config.in_analyze_full = value.lower() in ("true", "1", "yes")
                elif key == "in_daily_report":
                    config.in_daily_report = value.lower() in ("true", "1", "yes")
                elif key == "daily_report_top_n":
                    try:
                        config.daily_report_top_n = max(1, int(value))
                    except ValueError:
                        pass
    env = os.environ
    if env.get("DCF_IN_ANALYZE_FULL", "").strip():
        config.in_analyze_full = (
            env["DCF_IN_ANALYZE_FULL"].strip().lower() in ("true", "1", "yes")
        )
    if env.get("DCF_IN_DAILY_REPORT", "").strip():
        config.in_daily_report = (
            env["DCF_IN_DAILY_REPORT"].strip().lower() in ("true", "1", "yes")
        )
    if env.get("DCF_DAILY_REPORT_TOP_N", "").strip():
        try:
            config.daily_report_top_n = max(
                1, int(env["DCF_DAILY_REPORT_TOP_N"].strip())
            )
        except ValueError:
            pass
    return config


class RefreshService:
    """Ensure analyzed tickers are fresh and return their current prices."""

    def __init__(
        self,
        config: RefreshConfig | None = None,
        database_url: str | None = None,
        fdb_repo_path: str | None = None,
        price_service: PriceService | None = None,
        gateway: FdbGateway | None = None,
        sync_runner: Callable[[list[str], dict, str | None], int] | None = None,
        sec_health_fn: Callable[[], SecHealth] | None = None,
        metrics=None,
    ):
        self.config = config or load_refresh_config()
        self._gateway = gateway or FdbGateway(database_url)
        self._db_url = database_url
        self._fdb_repo_path = fdb_repo_path or os.environ.get(
            "FINANCIAL_DATABASE_REPO_PATH", DEFAULT_FDB_REPO
        )
        self._price_service = price_service or PriceService()
        # Injectable for tests; production uses _run_fdb_cli below.
        self._sync_runner = sync_runner
        # SEC availability preflight (backend/services/sec_health.py); the
        # probe itself is injectable so tests never touch the network.
        self._sec_health_fn = sec_health_fn or check_sec_availability
        # Optional run telemetry (NetworkMetrics): per-company sync counts,
        # retries and SEC 403/429 occurrences.
        self._metrics = metrics

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def ensure_fresh_and_prices(
        self,
        tickers: list[str],
        *,
        force: bool = False,
        max_age_hours: int | None = None,
        skip_refresh: bool | None = None,
        fetch_prices: bool = True,
        progress_cb: Callable[[str, bool | str], None] | None = None,
    ) -> RefreshResult:
        """Ensure freshness of the given tickers and fetch their prices.

        Only the passed tickers are considered — this is deliberately
        targeted; the full universe is never synced wholesale.

        Args:
            tickers: tickers being analyzed (case-insensitive).
            force: refresh every ticker regardless of age (CLI --refresh).
            max_age_hours: override the configured freshness threshold
                (CLI --freshness-hours).
            skip_refresh: skip the SEC sync step entirely (CLI --no-refresh
                or config skip_refresh_flag). Prices are still fetched.
            fetch_prices: when False, prices are not fetched.
            progress_cb: optional ``(ticker, status)`` hook invoked after
                every attempted sync (``status`` is True on success or the
                failure reason string). Used by the daily workflow to
                checkpoint progress; a raising callback is logged and never
                breaks the refresh.
        """
        threshold = (
            max_age_hours if max_age_hours is not None else self.config.freshness_max_age_hours
        )
        if skip_refresh is None:
            skip_refresh = self.config.skip_refresh_flag or not self.config.auto_refresh

        result = RefreshResult()

        if not self._gateway.available():
            result.notes.append(
                "Financial-DataBase unreachable — SEC refresh skipped; "
                "analysis will use whatever data exists"
            )
            skip_refresh = True

        if skip_refresh:
            result.notes.append("SEC refresh disabled (--no-refresh / skip_refresh_flag)")

        dedup: list[str] = []
        seen: set[str] = set()
        for ticker in tickers:
            t = ticker.strip().upper()
            if not t or t in seen:
                continue
            seen.add(t)
            dedup.append(t)

        work: list[tuple[str, str]] = []  # (ticker, CIK) companies to sync
        # No DB lookups at all when the refresh step is disabled, so that
        # --no-refresh keeps working on a totally unreachable database.
        meta = {} if skip_refresh else self._staleness_map(dedup)
        for ticker in dedup:
            if skip_refresh:
                # No sync requested: mark skipped without DB work; the only
                # cost later is the (optional) price fetch.
                result.skipped.append(ticker)
                continue

            company_id, cik, last = meta.get(ticker, (None, None, None))
            if company_id is None or cik is None:
                result.failed.append(
                    (ticker, "no CIK mapping in Financial-DataBase")
                )
                continue

            age_hours = None
            if last is not None:
                try:
                    age_hours = (
                        _dt.datetime.now(_dt.UTC) - last
                    ).total_seconds() / 3600.0
                except TypeError:
                    age_hours = None

            if force or last is None or age_hours is None or age_hours > threshold:
                work.append((ticker, cik))
            else:
                result.skipped.append(ticker)

        # SEC availability preflight: if EDGAR is rate-limiting or refusing
        # the request (403), skip every sync with one clear reason instead of
        # launching a burst of doomed subprocesses. Analysis proceeds with the
        # fundamentals already stored — prices come from Yahoo and are
        # unaffected.
        if work:
            health = self._probe_sec()
            if not health.available:
                reason = (
                    f"SEC unavailable ({health.reason}) — targeted refresh "
                    "skipped; analysis uses the stored fundamentals"
                )
                result.notes.append(reason)
                result.sec_skipped_reason = health.reason
                logger.warning("%s", reason)
                for ticker, _cik in work:
                    result.skipped.append(ticker)
                work = []

        # Targeted syncs. `sec sync` is subprocess-bound (the GIL is released
        # while waiting), so stale companies are synced concurrently up to
        # config.refresh_workers — a 2-3 worker pool roughly halves refresh
        # wall time while keeping the SEC burst modest.
        workers = max(1, int(self.config.refresh_workers or 1))
        if workers > 1 and len(work) > 1:
            outcomes = self._sync_many(work, workers, progress_cb=progress_cb)
            for ticker, _cik in work:  # order-preserving result grouping
                status = outcomes.get(ticker)
                if status is True:
                    result.refreshed.append(ticker)
                else:
                    result.failed.append((ticker, status))
        else:
            for ticker, cik in work:
                status = self._sync_company(cik)
                if status is True:
                    result.refreshed.append(ticker)
                else:
                    result.failed.append((ticker, status))
                self._notify_progress(progress_cb, ticker, status)

        if fetch_prices:
            result.prices = self._fetch_prices(dedup)

        return result

    def _sync_many(
        self,
        work: list[tuple[str, str]],
        workers: int,
        progress_cb: Callable[[str, bool | str], None] | None = None,
    ) -> dict[str, bool | str]:
        """Run several targeted CIK syncs concurrently.

        Each worker is a subprocess/runner call, so this is thread-safe: the
        only shared state is the ``outcomes`` dict built by the main thread
        as futures complete. ``progress_cb`` fires as each company finishes
        (not when the whole batch ends), so a long refresh can be
        checkpointed company by company.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        outcomes: dict[str, bool | str] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._sync_company, cik): ticker
                for ticker, cik in work
            }
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    outcomes[ticker] = future.result()
                except Exception as exc:  # noqa: BLE001 — never break the batch
                    outcomes[ticker] = f"SEC sync raised: {exc}"
                self._notify_progress(progress_cb, ticker, outcomes[ticker])
        return outcomes

    def check_freshness(
        self,
        tickers: list[str],
        *,
        max_age_hours: int | None = None,
    ) -> tuple[list[str], list[str], list[str]]:
        """Read-only staleness estimate: (stale, fresh, unknown) tickers.

        Never syncs anything and never touches prices — used for dry-run
        scope estimation (how many companies a real run would refresh) and
        for reporting the pre-run state. A ticker is "unknown" when it has
        no CIK mapping in Financial-DataBase or the DB is unreachable.
        """
        stale, fresh, unknown = self.staleness_ranked(
            tickers, max_age_hours=max_age_hours
        )
        return stale, fresh, unknown

    def staleness_ranked(
        self,
        tickers: list[str],
        *,
        max_age_hours: int | None = None,
    ) -> tuple[list[str], list[str], list[str]]:
        """One-pass staleness scan: ``(stale, fresh, unknown)``.

        ``stale`` is ordered by recency of the last sync (most recently
        synced first); companies never ingested sort last. This ordering
        lets the daily workflow apply --max-refresh by refreshing the stale
        companies whose data is closest to current and deferring the rest.
        Read-only — never syncs, never touches prices.
        """
        threshold = (
            max_age_hours
            if max_age_hours is not None
            else self.config.freshness_max_age_hours
        )
        ranked: list[tuple[float | None, str]] = []
        fresh: list[str] = []
        unknown: list[str] = []

        if not self._gateway.available():
            return [], [], self._dedup(tickers)

        now = _dt.datetime.now(_dt.UTC)
        meta = self._staleness_map(self._dedup(tickers))
        for ticker in self._dedup(tickers):
            company_id, _cik, last = meta.get(ticker, (None, None, None))
            if company_id is None:
                unknown.append(ticker)
                continue
            if last is None:
                ranked.append((None, ticker))  # never ingested → refreshable, oldest
                continue
            try:
                age_hours = (
                    now - last
                ).total_seconds() / 3600.0
            except TypeError:
                ranked.append((None, ticker))  # unparseable timestamp → treat as stale
                continue
            if age_hours > threshold:
                ranked.append((age_hours, ticker))
            else:
                fresh.append(ticker)

        # Most recently synced first; never-ingested (None) last.
        ranked.sort(key=lambda item: (item[0] is None, item[0] or 0.0))
        stale = [ticker for _, ticker in ranked]
        return stale, fresh, unknown

    # ------------------------------------------------------------------
    @staticmethod
    def _dedup(tickers: list[str]) -> list[str]:
        """Case-insensitive, order-preserving deduplication."""
        dedup: list[str] = []
        seen: set[str] = set()
        for ticker in tickers:
            t = ticker.strip().upper()
            if not t or t in seen:
                continue
            seen.add(t)
            dedup.append(t)
        return dedup

    def _staleness_map(
        self, tickers: list[str]
    ) -> dict[str, tuple[str | None, str | None, _dt.datetime | None]]:
        """Resolve (company_id, CIK, last sync time) for many tickers.

        Prefers the gateway's two-query bulk scan and transparently falls
        back to the sequential per-ticker resolve/last_synced_at path when
        the gateway does not implement it or the bulk query fails.
        """
        dedup = self._dedup(tickers)
        bulk = getattr(self._gateway, "staleness_bulk", None)
        if bulk is not None:
            try:
                return bulk(dedup)
            except Exception:  # noqa: BLE001 — fall back to per-ticker reads
                pass
        meta: dict[
            str, tuple[str | None, str | None, _dt.datetime | None]
        ] = {}
        for ticker in dedup:
            try:
                resolved = self._gateway.resolve_company(ticker)
            except Exception:  # noqa: BLE001
                resolved = None
            if resolved is None:
                meta[ticker] = (None, None, None)
                continue
            company_id, cik = resolved
            last = None
            try:
                last = self._gateway.last_synced_at(company_id)
            except Exception:  # noqa: BLE001
                last = None
            meta[ticker] = (company_id, cik, last)
        return meta

    def _fetch_prices(self, tickers: list[str]) -> dict[str, float | None]:
        try:
            return self._price_service.get_current_prices(tickers)
        except Exception:  # noqa: BLE001 — prices must never break the command
            return {}

    def _probe_sec(self) -> SecHealth:
        """Run the injectable SEC preflight; never let it break the command."""
        try:
            return self._sec_health_fn()
        except Exception as exc:  # noqa: BLE001 — probe failure ≠ command failure
            return SecHealth(False, f"SEC preflight failed: {exc}", None, 0.0)

    @staticmethod
    def _notify_progress(
        progress_cb: Callable[[str, bool | str], None] | None,
        ticker: str,
        status: bool | str,
    ) -> None:
        """Fire the optional progress hook; never let it break the refresh."""
        if progress_cb is None:
            return
        try:
            progress_cb(ticker, status)
        except Exception as exc:  # noqa: BLE001 — checkpointing must not crash
            logger.warning("progress callback failed for %s: %s", ticker, exc)

    def sync_one(self, cik: str) -> bool | str:
        """Targeted ``sec sync`` for a single CIK (public entry point).

        Exposed for tools that drive syncs outside a ticker universe (see
        ``scripts/catch_up_stale.py``). Never syncs anything else: the SEC
        ingestion is always per-CIK, never a database-wide sweep.
        """
        return self._sync_company(cik)

    def _sync_company(self, cik: str) -> bool | str:
        """Run a targeted sec sync for one CIK. True on success, reason on failure.

        Each attempt is timed and reported to the run telemetry: a sync is the
        unit of SEC work this service performs (the actual HTTP calls happen
        in the Financial-DataBase subprocess), and the failure reason is
        scanned for HTTP 403/429 so SEC throttling shows up in the report.
        """
        if self._sync_runner is not None:
            started = time.time()
            status = self._sync_runner(cik)
        else:
            started = time.time()
            status = self._run_fdb_cli(cik)
        latency_ms = (time.time() - started) * 1000.0
        if self._metrics is not None:
            try:
                if status is True:
                    self._metrics.record("sec", latency_ms=latency_ms)
                else:
                    self._metrics.record_failure(
                        "sec", str(status), latency_ms=latency_ms
                    )
            except Exception:  # noqa: BLE001 — telemetry must not break a sync
                pass
        return status

    def _run_fdb_cli(self, cik: str) -> bool | str:
        """Invoke `financial-db sec sync <CIK>` in the Financial-DataBase venv."""
        user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
        if not user_agent:
            return (
                "SEC_USER_AGENT not set — targeted refresh requires it "
                "(documented in Financial-DataBase/.env.example)"
            )

        repo = self._fdb_repo_path
        python = os.path.join(repo, ".venv", "bin", "python")
        if not os.path.exists(python):
            python = "python3"

        cmd = [python, "-m", "financial_database.cli", "sec", "sync", cik]
        env = dict(os.environ)
        env["SEC_USER_AGENT"] = user_agent
        if self._db_url:
            env["DATABASE_URL"] = self._db_url
        env.setdefault("DATA_RAW_DIR", os.path.join(repo, "data", "raw"))

        try:
            completed = subprocess.run(
                cmd,
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.config.refresh_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return (
                f"SEC sync timed out after {self.config.refresh_timeout_seconds}s"
            )
        except FileNotFoundError:
            return f"Financial-DataBase CLI not runnable at {repo}"
        except Exception as exc:  # noqa: BLE001
            return f"SEC sync failed to start: {exc}"

        if completed.returncode == 0:
            return True

        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        detail = tail[-1] if tail else "unknown error"
        return f"SEC sync failed ({completed.returncode}): {detail[:200]}"