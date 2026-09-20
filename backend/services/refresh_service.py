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
- If SEC is unreachable or the sync times out, the company is reported as
  failed and analysis proceeds with the data that exists.
"""

from __future__ import annotations

import datetime as _dt
import os
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Optional

from backend.services.price_service import PriceService

# Defaults for config/refresh.yaml (the file itself is optional and only
# overrides these).
DEFAULT_AUTO_REFRESH = True
DEFAULT_FRESHNESS_MAX_AGE_HOURS = 168  # 7 days
DEFAULT_REFRESH_TIMEOUT_SECONDS = 300
DEFAULT_SKIP_REFRESH_FLAG = False

# Well-known location of the Financial-DataBase checkout, overridable with
# FINANCIAL_DATABASE_REPO_PATH.
DEFAULT_FDB_REPO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Financial-DataBase",
)


@dataclass
class RefreshConfig:
    """Behavior of the on-demand refresh step, from config/refresh.yaml."""

    auto_refresh: bool = DEFAULT_AUTO_REFRESH
    freshness_max_age_hours: int = DEFAULT_FRESHNESS_MAX_AGE_HOURS
    refresh_timeout_seconds: int = DEFAULT_REFRESH_TIMEOUT_SECONDS
    skip_refresh_flag: bool = DEFAULT_SKIP_REFRESH_FLAG


@dataclass
class RefreshResult:
    """Outcome of ensure_fresh_and_prices for one batch of tickers."""

    refreshed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    prices: dict[str, Optional[float]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


class FdbGateway:
    """Read-only access to Financial-DataBase (companies, freshness).

    Only reads metadata and ingestion timestamps; never writes. Prices are
    not part of this gateway — they flow through PriceService.
    """

    def __init__(self, database_url: Optional[str] = None):
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
        except Exception:
            return False

    # ------------------------------------------------------------------
    def resolve_company(self, ticker: str) -> Optional[tuple[str, str]]:
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
        except Exception:
            return None
        if not row:
            return None
        return str(row["company_id"]), str(row["cik"])

    def last_synced_at(self, company_id: str) -> Optional[_dt.datetime]:
        """Last ingestion timestamp for a company, from data timestamps.

        import_runs has no per-CIK scope, so freshness is derived from the
        most recent fact/filing write for that company.
        """
        try:
            with self._connection().cursor() as cur:
                cur.execute(
                    """
                    SELECT GREATEST(
                        (SELECT max(updated_at) FROM financial_facts WHERE company_id = %s),
                        (SELECT max(created_at) FROM filings WHERE company_id = %s)
                    ) AS last_ingested
                    """,
                    (company_id, company_id),
                )
                row = cur.fetchone()
        except Exception:
            return None
        if not row or row["last_ingested"] is None:
            return None
        value = row["last_ingested"]
        if isinstance(value, _dt.datetime):
            return value
        return _dt.datetime.fromisoformat(str(value))


def load_refresh_config(path: Optional[str] = None) -> RefreshConfig:
    """Load config/refresh.yaml into a RefreshConfig.

    The YAML file is intentionally tiny (flat ``key: value`` pairs), so it
    is parsed without a YAML dependency. Missing file or keys fall back to
    the defaults; environment variables win over the file:
      REFRESH_AUTO, FRESHNESS_MAX_AGE_HOURS, REFRESH_TIMEOUT_SECONDS,
      REFRESH_SKIP_FLAG
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

    return config


class RefreshService:
    """Ensure analyzed tickers are fresh and return their current prices."""

    def __init__(
        self,
        config: Optional[RefreshConfig] = None,
        database_url: Optional[str] = None,
        fdb_repo_path: Optional[str] = None,
        price_service: Optional[PriceService] = None,
        gateway: Optional[FdbGateway] = None,
        sync_runner: Optional[Callable[[list[str], dict, Optional[str]], int]] = None,
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

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def ensure_fresh_and_prices(
        self,
        tickers: list[str],
        *,
        force: bool = False,
        max_age_hours: Optional[int] = None,
        skip_refresh: Optional[bool] = None,
        fetch_prices: bool = True,
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

        dedup: dict[str, Optional[tuple[Optional[str], Optional[str]]]] = {}
        for ticker in tickers:
            t = ticker.strip().upper()
            if not t or t in dedup:
                continue
            dedup[t] = self._gateway.resolve_company(t)

        for ticker, resolved in dedup.items():
            company_id = cik = None
            if resolved is not None:
                company_id, cik = resolved
            if company_id is None or cik is None:
                result.failed.append(
                    (ticker, "no CIK mapping in Financial-DataBase")
                )
                continue

            if skip_refresh:
                result.skipped.append(ticker)
                continue

            try:
                last = self._gateway.last_synced_at(company_id)
            except Exception as exc:  # noqa: BLE001
                result.failed.append((ticker, f"freshness check failed: {exc}"))
                last = None

            age_hours = None
            if last is not None:
                age_hours = (
                    _dt.datetime.now(_dt.timezone.utc) - last
                ).total_seconds() / 3600.0

            if force or last is None or age_hours is None or age_hours > threshold:
                status = self._sync_company(cik)
                if status is True:
                    result.refreshed.append(ticker)
                else:
                    result.failed.append((ticker, status))
            else:
                result.skipped.append(ticker)

        if fetch_prices:
            result.prices = self._fetch_prices([t for t in dedup])

        return result

    # ------------------------------------------------------------------
    def _fetch_prices(self, tickers: list[str]) -> dict[str, Optional[float]]:
        try:
            return self._price_service.get_current_prices(tickers)
        except Exception:  # noqa: BLE001 — prices must never break the command
            return {}

    def _sync_company(self, cik: str) -> bool | str:
        """Run a targeted sec sync for one CIK. True on success, reason on failure."""
        if self._sync_runner is not None:
            return self._sync_runner(cik)
        return self._run_fdb_cli(cik)

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