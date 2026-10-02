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


# ---------------------------------------------------------------------------
# Balance-sheet fixtures (parsed from the real documents)
# ---------------------------------------------------------------------------
BALANCE_SHEET_TICKERS = ("AAPL", "KO", "JNJ", "JPM")


def build_balance_sheets() -> int:
    """Fetch each ticker's latest 10-K and snapshot the parsed balance sheet."""
    import json as _json
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from backend.services.balance_sheet_parser import BalanceSheetParser
    from backend.services.filing_fetcher import FilingFetcher
    from backend.services.filing_service import FilingService

    target_dir = PROJECT_ROOT / "data" / "demo" / "balance_sheets"
    target_dir.mkdir(parents=True, exist_ok=True)
    service = FilingService()
    fetcher = FilingFetcher()
    parser = BalanceSheetParser()
    written = 0

    for ticker in BALANCE_SHEET_TICKERS:
        filings = service.list_filings(ticker, form_types=["10-K"])
        if not filings:
            print(f"{ticker}: no 10-K in the database, skipped")
            continue
        record = filings[0]
        html = fetcher.fetch_html(
            record.cik, record.accession_number, record.primary_document
        )
        if html is None:
            print(f"{ticker}: could not fetch {record.accession_number}, skipped")
            continue
        sheet = parser.parse(
            html,
            filing_date=record.filing_date,
            period_end=record.period_of_report,
            form_type=record.form_type,
        )
        if sheet is None:
            print(f"{ticker}: parser found no balance sheet, skipped")
            continue
        period = (
            record.period_of_report.isoformat()
            if record.period_of_report
            else "unknown"
        )
        payload = {
            "ticker": ticker,
            "form_type": record.form_type,
            "filing_date": record.filing_date.isoformat(),
            "period_end": period,
            "accession_number": record.accession_number,
            "source": sheet.source,
            "periods": list(sheet.header_periods),
            "extraction_warnings": sheet.extraction_warnings,
            "lines": [
                {
                    "label": line.label,
                    "current": line.current,
                    "prior": line.prior,
                    "indent_level": line.indent_level,
                }
                for line in sheet.lines
            ],
        }
        target = target_dir / f"{ticker}_{record.form_type}_{period}.json"
        target.write_text(
            _json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written += 1
        print(f"{ticker}: {len(sheet.lines)} lines ({sheet.source}) -> {target.name}")
    return written


if __name__ == "__main__":
    raise SystemExit(0 if build_balance_sheets() >= 0 else 1)
