"""Resolve a ticker against Financial-DataBase listings (CLI preflight).

Read-only: one indexed lookup on ``company_listings``. A database failure
raises so callers can decide whether to degrade (the CLI proceeds with the
analysis) or stop; an unknown ticker returns ``None``.
"""

from __future__ import annotations

import os

import psycopg2

DEFAULT_URL = "postgresql://financial:test@localhost:5432/financial_database"


def _fdb_url() -> str:
    return os.environ.get("FINANCIAL_DATABASE_URL", DEFAULT_URL)


def resolve_ticker(ticker: str) -> str | None:
    """Normalized ticker when an active FDB listing exists, else None."""
    normalized = (ticker or "").strip().upper()
    if not normalized:
        return None
    with psycopg2.connect(_fdb_url()) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM company_listings "
            "WHERE UPPER(ticker) = %s AND is_active LIMIT 1",
            (normalized,),
        )
        return normalized if cur.fetchone() else None
