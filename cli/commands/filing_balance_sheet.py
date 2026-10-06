"""`filing-balance-sheet` — extract the balance sheet from a 10-K/10-Q."""

from __future__ import annotations

from backend.app.cli import add_demo_argument
from cli.formatters import dim, print_header, red, yellow


def register(subparsers):
    p = subparsers.add_parser(
        "filing-balance-sheet",
        help="Extract and print the balance sheet from a 10-K/10-Q",
        description=(
            "Finds the matching filing, fetches its HTML (cached under "
            "data/raw/filings/), parses the balance sheet and prints the "
            "values exactly as filed."
        ),
    )
    p.add_argument("ticker", help="Ticker (e.g. AAPL)")
    p.add_argument("--accession", help="Specific accession number")
    p.add_argument("--form", help="Form type filter (default: 10-K, 10-Q, 20-F, 40-F)")
    p.add_argument("--year", type=int, help="Fiscal year filter")
    p.add_argument(
        "--raw",
        action="store_true",
        help="Plain label/value rows instead of the formatted table",
    )
    add_demo_argument(p)
    p.set_defaults(func=_run)


def _run(args):
    from backend.services.balance_sheet_parser import load_balance_sheet
    from backend.services.filing_service import DEFAULT_FORM_TYPES, FilingService

    ticker = args.ticker.upper().strip()
    service = FilingService()

    if args.accession:
        candidates = [
            record
            for record in service.list_filings(ticker, form_types=None)
            if record.accession_number == args.accession
        ]
    else:
        candidates = service.list_filings(
            ticker,
            form_types=[args.form.upper()] if args.form else list(DEFAULT_FORM_TYPES),
            fiscal_years=[args.year] if args.year else None,
        )
    if not candidates:
        print(yellow(f"No filings for {ticker} match the filters."))
        return

    record = candidates[0]  # newest first
    sheet = load_balance_sheet(record)
    header = (
        f"Balance Sheet — {ticker} {record.form_type} filed "
        f"{record.filing_date.isoformat()}"
    )
    if record.period_of_report:
        header += f" (period {record.period_of_report.isoformat()})"
    print_header(header)

    if sheet is None:
        print(red("Could not extract the balance sheet from this document."))
        if record.sec_url:
            print(f"  Original: {record.sec_url}")
        return

    current, prior = sheet.header_periods
    current_label = current or "Current"
    prior_label = prior or "Prior"
    if args.raw:
        for line in sheet.lines:
            print(f"{line.label} | {line.current or ''} | {line.prior or ''}")
    else:
        width = max((len(line.label) for line in sheet.lines), default=20)
        width = min(max(width, 30), 58)
        print(f"  {'Line item':<{width}} {current_label:<16} {prior_label:<16}")
        print("  " + "─" * (width + 34))
        for line in sheet.lines:
            label = ("  " * line.indent_level) + line.label
            print(f"  {label:<{width}} {line.current or '':<16} {line.prior or '':<16}")
    print()
    print(f"  Source: SEC EDGAR · Extraction: {sheet.source}")
    if record.sec_url:
        print(f"  Original: {record.sec_url}")
    if sheet.extraction_warnings:
        print(f"  {dim(sheet.extraction_warnings[0])}")
