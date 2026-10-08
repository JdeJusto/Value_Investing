"""Company and listing lookups (ids, names, sectors, CIK).

Mixin for :class:`FinancialDatabaseRepository` (pure move).
"""

from __future__ import annotations


class LookupsMixin:
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

    def get_sector_map(
        self, tickers: list[str] | tuple[str, ...]
    ) -> dict[str, str | None]:
        """Sector per ticker in ONE metadata query (active listings).

        Tickers missing from the database (or not yet sector-enriched) map to
        None. Read-only metadata; never touches prices.
        """
        wanted = sorted({str(t).upper() for t in tickers if str(t).strip()})
        if not wanted:
            return {}
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT UPPER(cl.ticker) AS ticker, c.sector
                    FROM company_listings cl
                    JOIN companies c ON c.id = cl.company_id
                    WHERE UPPER(cl.ticker) = ANY(%s) AND cl.is_active
                    """,
                    (wanted,),
                )
                return {row["ticker"]: row["sector"] for row in cur.fetchall()}
        except Exception:  # noqa: BLE001 — a DB failure reads as "no sector"
            return {}

    def search_companies(self, query: str, limit: int = 20) -> list[dict]:
        """Ticker prefix/substring matches, then legal-name substring matches.

        Returns ``[{"ticker", "name", "sector"}]``: exact-ticker matches
        first, then prefix matches, then substring matches; when fewer than
        ``limit`` rows match the ticker, legal-name substring matches fill the
        rest. Read-only metadata (companies + active listings).
        """
        q = str(query or "").strip().upper()
        limit = max(int(limit), 0)
        if not q or limit == 0:
            return []
        found: list[dict] = []
        seen: set[str] = set()

        def _add(row) -> None:
            if row["ticker"] not in seen:
                seen.add(row["ticker"])
                found.append(
                    {
                        "ticker": row["ticker"],
                        "name": row["name"],
                        "sector": row["sector"],
                    }
                )

        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT UPPER(cl.ticker) AS ticker, c.legal_name AS name,
                           c.sector AS sector
                    FROM company_listings cl
                    JOIN companies c ON c.id = cl.company_id
                    WHERE cl.is_active AND UPPER(cl.ticker) LIKE %s
                    ORDER BY (UPPER(cl.ticker) = %s) DESC,
                             (UPPER(cl.ticker) LIKE %s) DESC,
                             cl.ticker
                    LIMIT %s
                    """,
                    (f"%{q}%", q, f"{q}%", limit),
                )
                for row in cur.fetchall():
                    _add(row)
                if len(found) < limit:
                    cur.execute(
                        """
                        SELECT UPPER(cl.ticker) AS ticker, c.legal_name AS name,
                               c.sector AS sector
                        FROM company_listings cl
                        JOIN companies c ON c.id = cl.company_id
                        WHERE cl.is_active AND UPPER(c.legal_name) LIKE %s
                        ORDER BY cl.ticker
                        LIMIT %s
                        """,
                        (f"%{q}%", limit - len(found)),
                    )
                    for row in cur.fetchall():
                        _add(row)
        except Exception:  # noqa: BLE001 — a DB failure reads as "no match"
            return []
        return found[:limit]

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
