"""Read-only gateway to Financial-DataBase (companies, freshness).

Pure move out of ``refresh_service``: it only reads metadata and ingestion
timestamps, never writes. Prices are not part of this gateway — they flow
through PriceService.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os

# Same logger name as before the split, so log routing is unchanged.
logger = logging.getLogger("backend.refresh_service")


class FdbGateway:
    """Read-only access to Financial-DataBase (companies, freshness).

    Only reads metadata and ingestion timestamps; never writes. Prices are
    not part of this gateway — they flow through PriceService.
    """

    def __init__(self, database_url: str | None = None):
        if database_url is None:
            database_url = os.environ.get(
                "FINANCIAL_DATABASE_URL",
                # Local development default; override with the env var.
                "postgresql://financial:test@localhost:5432/financial_database",
            )
        self.database_url = database_url
        self._conn = None

    # ------------------------------------------------------------------
    def _connection(self):
        import psycopg2
        from psycopg2.extras import RealDictCursor

        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                self.database_url, cursor_factory=RealDictCursor
            )
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
