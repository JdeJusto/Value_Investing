"""Snapshot real SEC filing rows from Financial-DataBase into demo fixtures.

The demo bundle must stay self-contained, so the filings tab reads
``data/demo/filings/<TICKER>.json`` instead of the database. This script
copies the most recent rows per demo ticker (real accessions and dates, so
the EDGAR index links work) and pins them.

Usage (requires a reachable Financial-DataBase)::

    python -m scripts.build_demo_filings
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_FILINGS = PROJECT_ROOT / "data" / "demo" / "filings"

TICKERS = ("AAPL", "MSFT", "KO", "JNJ", "JPM", "XOM", "PLD", "TSLA")
#: Per ticker: the forms worth shipping, newest first.
FORMS = ("10-K", "10-Q", "8-K")

URL = os.environ.get(
    "FINANCIAL_DATABASE_URL",
    "postgresql://financial:test@localhost:5432/financial_database",
)

SQL = text(
    """
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
    JOIN companies c ON c.id = f.company_id
    JOIN company_identifiers ci
      ON ci.company_id = c.id
     AND ci.identifier_type = 'CIK'
    JOIN company_listings cl ON cl.company_id = c.id AND cl.is_active = true
    WHERE UPPER(cl.ticker) = :ticker
      AND f.form = ANY(:forms)
    ORDER BY f.filing_date DESC
    LIMIT 8
    """
)


def main() -> int:
    engine = create_engine(URL)
    DEMO_FILINGS.mkdir(parents=True, exist_ok=True)
    total = 0
    with engine.connect() as conn:
        for ticker in TICKERS:
            rows = (
                conn.execute(SQL, {"ticker": ticker, "forms": list(FORMS)})
                .mappings()
                .all()
            )
            payload = []
            for row in rows:
                payload.append(
                    {
                        "accession_number": row["accession_number"],
                        "form": row["form"],
                        "filing_date": row["filing_date"].isoformat(),
                        "period_end": (
                            row["period_end"].isoformat() if row["period_end"] else None
                        ),
                        "fiscal_year": row["fiscal_year"],
                        "fiscal_period": row["fiscal_period"],
                        "is_amended": bool(row["is_amended"]),
                        "filing_url": row["filing_url"],
                        "cik": row["cik"],
                        "demo_placeholder": False,
                    }
                )
            target = DEMO_FILINGS / f"{ticker}.json"
            target.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            total += len(payload)
            print(f"{ticker}: {len(payload)} filings -> {target.name}")
    print(f"total {total} filings snapshotted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
