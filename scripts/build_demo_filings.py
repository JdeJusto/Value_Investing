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


# (the `--sections` dispatch lives at the end of the file, after the builders)


# ---------------------------------------------------------------------------
# Narrative-section fixtures (Risk Factors and MD&A, 20 KB each)
# ---------------------------------------------------------------------------
SECTION_TICKERS = ("AAPL", "KO", "JNJ", "JPM")
MAX_FIXTURE_BYTES = 20_000  # keep the demo bundle small


def build_section_fixtures() -> int:
    """Extract each ticker's Risk Factors and MD&A into 20 KB demo fixtures."""
    import json as _json
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from backend.services.filing_service import FilingService
    from backend.services.narrative_extractor import (
        NARRATIVE_PARSER_VERSION,
        NarrativeExtractor,
        SectionType,
    )

    target_dir = PROJECT_ROOT / "data" / "demo" / "sections"
    target_dir.mkdir(parents=True, exist_ok=True)
    service = FilingService()
    extractor = NarrativeExtractor()
    cache_root = PROJECT_ROOT / "data" / "raw" / "filings"
    written = 0

    for ticker in SECTION_TICKERS:
        filings = service.list_filings(ticker, form_types=["10-K"])
        if not filings:
            print(f"{ticker}: no 10-K, skipped")
            continue
        record = filings[0]
        # Resolve the cached 10-K HTML directly (the local listing may not
        # carry primary_document; the cache tree is authoritative here).
        cik_dir = (
            cache_root / str(int(record.cik))
            if str(record.cik).isdigit()
            else cache_root / str(record.cik)
        )
        acc_dir = cik_dir / record.accession_number.replace("-", "")
        cached_docs = sorted(acc_dir.glob("*.htm")) if acc_dir.exists() else []
        if not cached_docs:
            print(f"{ticker}: no cached HTML for {record.accession_number}, skipped")
            continue
        html = cached_docs[0].read_text(encoding="utf-8", errors="replace")
        for section_type in (SectionType.RISK_FACTORS, SectionType.MD_A):
            section = extractor.extract(
                html,
                section_type,
                form_type=record.form_type,
                filing_date=record.filing_date,
                period_end=record.period_of_report,
            )
            if section is None:
                print(f"{ticker} {section_type.value}: not found")
                continue
            text = section.text[:MAX_FIXTURE_BYTES]
            warnings = list(section.extraction_warnings)
            if len(section.text) > MAX_FIXTURE_BYTES:
                warnings.append("truncated to 20 KB for demo bundle")
            if len(section.text.split()) < 300:
                warnings.append(
                    f"very short section ({len(section.text.split())} words); the "
                    "filing likely incorporates this narrative by reference "
                    "instead of carrying it in the document"
                )
            period = (
                record.period_of_report.isoformat()
                if record.period_of_report
                else "unknown"
            )
            payload = {
                "version": NARRATIVE_PARSER_VERSION,
                "section_type": section_type.value,
                "filing_date": record.filing_date.isoformat(),
                "period_end": period,
                "form_type": record.form_type,
                "title": section.title,
                "text": text,
                "word_count": len(text.split()),
                "source": section.source,
                "extraction_warnings": warnings,
            }
            target = target_dir / f"{ticker}_{section_type.value}.json"
            target.write_text(
                _json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            written += 1
            print(
                f"{ticker} {section_type.value}: {len(text) // 1024} KB "
                f"({payload['word_count']} words) -> {target.name}"
            )
    print(f"total {written} narrative section fixtures")
    return 0 if written else 1


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


# (the `__main__` dispatch lives at the end of the file)


# ---------------------------------------------------------------------------
# Statement fixtures: 4 tickers x 3 statement types
# ---------------------------------------------------------------------------
STATEMENT_TICKERS = ("AAPL", "KO", "JNJ", "JPM")
MAX_FIXTURE_LINES = 50


def build_statement_fixtures() -> int:
    """Parse each ticker's latest 10-K into the three statement fixtures."""
    import json as _json
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from backend.services.filing_fetcher import FilingFetcher
    from backend.services.filing_service import FilingService
    from backend.services.financial_statement_parser import (
        PARSER_VERSION,
        FinancialStatementParser,
        StatementType,
    )

    target_dir = PROJECT_ROOT / "data" / "demo" / "statements"
    target_dir.mkdir(parents=True, exist_ok=True)
    service = FilingService()
    fetcher = FilingFetcher()
    parser = FinancialStatementParser()
    written = 0

    for ticker in STATEMENT_TICKERS:
        filings = service.list_filings(ticker, form_types=["10-K"])
        if not filings:
            print(f"{ticker}: no 10-K, skipped")
            continue
        record = filings[0]
        html = fetcher.fetch_html(
            record.cik, record.accession_number, record.primary_document
        )
        if html is None:
            print(f"{ticker}: fetch failed, skipped")
            continue
        for statement_type in StatementType:
            statement = parser.parse(
                html,
                statement_type,
                filing_date=record.filing_date,
                period_end=record.period_of_report,
                form_type=record.form_type,
            )
            if statement is None:
                print(f"{ticker} {statement_type.value}: not found")
                continue
            lines = statement.lines[:MAX_FIXTURE_LINES]
            warnings = list(statement.extraction_warnings)
            if len(statement.lines) > MAX_FIXTURE_LINES:
                warnings.append(
                    f"truncated to the first {MAX_FIXTURE_LINES} lines "
                    f"(of {len(statement.lines)}) to keep the demo bundle small"
                )
            period = (
                record.period_of_report.isoformat()
                if record.period_of_report
                else "unknown"
            )
            payload = {
                "version": PARSER_VERSION,
                "statement_type": statement_type.value,
                "filing_date": record.filing_date.isoformat(),
                "period_end": period,
                "form_type": record.form_type,
                "source": statement.source,
                "periods": list(statement.header_periods),
                "extraction_warnings": warnings,
                "lines": [
                    {
                        "label": line.label,
                        "current": line.current,
                        "prior": line.prior,
                        "indent_level": line.indent_level,
                    }
                    for line in lines
                ],
            }
            target = target_dir / f"{ticker}_{statement_type.value}_{period}.json"
            target.write_text(
                _json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            written += 1
            print(
                f"{ticker} {statement_type.value}: {len(lines)} lines -> {target.name}"
            )
    return written


if __name__ == "__main__":
    import sys as _sys

    if len(_sys.argv) > 1 and _sys.argv[1] == "--sections":
        raise SystemExit(build_section_fixtures())
    raise SystemExit(main())
