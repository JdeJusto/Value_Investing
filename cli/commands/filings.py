"""`filings` — official SEC filings for a ticker, with EDGAR links."""

from __future__ import annotations

import argparse
from datetime import date

from backend.app.cli import add_demo_argument
from cli.formatters import dim, print_header, print_table, red


def register(subparsers):
    p = subparsers.add_parser(
        "filings",
        help="List official SEC filings (10-K, 10-Q, 8-K, ...) with EDGAR links",
        description=(
            "Reads the filings table from Financial-DataBase and builds the "
            "SEC EDGAR URLs. Nothing is downloaded here: the links open the "
            "official documents on sec.gov."
        ),
    )
    p.add_argument("ticker", help="Ticker (e.g. AAPL)")
    p.add_argument(
        "--form", type=str, help="Form types, comma-separated (e.g. 10-K,10-Q)"
    )
    p.add_argument("--year", type=int, action="append", help="Fiscal year (repeatable)")
    p.add_argument("--since", type=str, help="Only filings on/after YYYY-MM-DD")
    p.add_argument(
        "--all",
        action="store_true",
        help="Every form type (default: 10-K, 10-Q, 20-F, 40-F)",
    )
    p.add_argument(
        "--urls",
        action="store_true",
        help="Add a column with the raw EDGAR URLs",
    )
    p.add_argument("--limit", type=int, default=40, help="Max rows (default 40)")
    p.add_argument(
        "--open",
        nargs="?",
        const=0,
        type=int,
        default=None,
        help="Open the newest match (--open) or the Nth row (--open 3)",
    )
    p.add_argument(
        "--prompt-open",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    add_demo_argument(p)
    p.set_defaults(func=_run)


def _run(args):
    from backend.services.filing_service import DEFAULT_FORM_TYPES, FilingService

    ticker = args.ticker.upper().strip()
    form_types = None
    if args.form:
        form_types = [
            form.strip().upper() for form in args.form.split(",") if form.strip()
        ]
    elif not args.all:
        form_types = list(DEFAULT_FORM_TYPES)

    since = None
    if args.since:
        try:
            since = date.fromisoformat(args.since)
        except ValueError:
            print(red(f"Invalid date: {args.since} (use YYYY-MM-DD)"))
            return

    name = None
    try:
        from backend.app.cli import build_financial_repository

        name = build_financial_repository().get_company_name(ticker)
    except Exception:  # noqa: BLE001 — the name is cosmetic
        name = None

    try:
        records = FilingService().list_filings(
            ticker,
            form_types=form_types,
            fiscal_years=args.year or None,
            start_date=since,
            limit=args.limit,
        )
    except Exception as exc:  # noqa: BLE001 — boundary catch-all (DB/network)
        print(red(f"ERROR: could not read filings for {ticker}: {exc}"))
        return

    print_header(f"Filings — {ticker}" + (f" ({name})" if name else ""))
    if not records:
        print("  No filings match the filters. Try --all or a wider date range.")
        return

    rows = []
    for index, record in enumerate(records, start=1):
        period = record.period_of_report.isoformat() if record.period_of_report else "—"
        fiscal_year = (
            str(record.effective_fiscal_year) if record.effective_fiscal_year else "—"
        )
        row = [
            str(index),
            record.form_type,
            record.filing_date.isoformat(),
            period,
            fiscal_year,
            record.accession_number,
        ]
        if getattr(args, "urls", False):
            row.append(_edgar_url(record))
        rows.append(row)
    headers = [
        ("#", 1),
        ("Form", 0),
        ("Filed", 0),
        ("Period", 0),
        ("FY", 0),
        ("Accession", 0),
    ]
    if getattr(args, "urls", False):
        headers.append(("URL", 0))
    print_table(headers, rows)

    print()
    print(f"  Total: {len(records)} filings")
    filters = []
    if form_types:
        filters.append(f"form_types={form_types}")
    if args.year:
        filters.append(f"years={args.year}")
    if since:
        filters.append(f"since={since.isoformat()}")
    if filters:
        print(f"  Filtered by: {', '.join(filters)}")

    print(
        dim(
            f"  Open: vi filing open {ticker} <N>  ·  "
            f"or: vi filings {ticker} --open <N>"
        )
    )

    open_index = getattr(args, "open", None)
    if open_index is not None:
        position = open_index if open_index > 0 else 1
        if position > len(records):
            print(red(f"--open {position}: out of range (1-{len(records)})"))
            return
        _open_records(records, position)

    if getattr(args, "prompt_open", False):
        _prompt_open(records)


def _edgar_url(record) -> str:
    from backend.services.filing_service import filing_edgar_url

    return filing_edgar_url(record.accession_number, getattr(record, "cik", "")) or (
        getattr(record, "sec_url", "") or ""
    )


def _open_records(records, position: int) -> None:
    from cli.commands.filing import _open_url

    _open_url(_edgar_url(records[position - 1]))


def _prompt_open(records) -> None:
    try:
        raw = input(
            f"\n  Open a filing in browser? [1-{len(records)}, Enter to skip]: "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not raw:
        return
    try:
        position = int(raw)
    except ValueError:
        return
    if 1 <= position <= len(records):
        _open_records(records, position)
