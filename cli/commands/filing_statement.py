"""`filing-statement` — extract any financial statement from a 10-K/10-Q.

Consolidated command with a ``--type`` selector; ``filing-income-statement``
and ``filing-cash-flow`` are thin aliases. The v0.6.0
``filing-balance-sheet`` command keeps working unchanged.
"""

from __future__ import annotations

from backend.app.cli import add_demo_argument
from cli.formatters import dim, print_header, red, yellow


def _register_one(subparsers, name: str, help_text: str, default_type: str | None):
    p = subparsers.add_parser(name, help=help_text, description=help_text)
    p.add_argument("ticker", help="Ticker (e.g. AAPL)")
    if default_type is None:
        p.add_argument(
            "--type",
            default="balance_sheet",
            choices=["balance_sheet", "income_statement", "cash_flow"],
            help="Statement type (default: balance_sheet)",
        )
    p.add_argument("--accession", help="Specific accession number")
    p.add_argument("--form", help="Form type filter (default: 10-K, 10-Q, 20-F, 40-F)")
    p.add_argument("--year", type=int, help="Fiscal year filter")
    p.add_argument(
        "--raw", action="store_true", help="Plain label/value rows instead of a table"
    )
    add_demo_argument(p)
    p.set_defaults(func=_run, statement_default=default_type)
    return p


def register(subparsers):
    _register_one(
        subparsers,
        "filing-statement",
        "Extract a financial statement (balance sheet, income, cash flow) from a filing",
        None,
    )
    _register_one(
        subparsers,
        "filing-income-statement",
        "Extract the income statement from a 10-K/10-Q",
        "income_statement",
    )
    _register_one(
        subparsers,
        "filing-cash-flow",
        "Extract the cash flow statement from a 10-K/10-Q",
        "cash_flow",
    )


def _run(args):
    from backend.services.filing_service import DEFAULT_FORM_TYPES, FilingService
    from backend.services.financial_statement_parser import (
        StatementType,
        load_financial_statement,
    )

    raw_type = getattr(args, "statement_default", None) or args.type
    statement_type = StatementType(raw_type)

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

    record = candidates[0]
    statement = load_financial_statement(record, statement_type)
    header = (
        f"{statement_type.label} — {ticker} {record.form_type} filed "
        f"{record.filing_date.isoformat()}"
    )
    if record.period_of_report:
        header += f" (period {record.period_of_report.isoformat()})"
    print_header(header)

    if statement is None:
        print(red(f"Could not extract the {statement_type.label} from this document."))
        if record.sec_url:
            print(f"  Original: {record.sec_url}")
        return

    current, prior = statement.header_periods
    current_label = current or "Current"
    prior_label = prior or "Prior"
    if args.raw:
        for line in statement.lines:
            print(f"{line.label} | {line.current or ''} | {line.prior or ''}")
    else:
        width = max((len(line.label) for line in statement.lines), default=20)
        width = min(max(width, 30), 58)
        print(f"  {'Line item':<{width}} {current_label:<16} {prior_label:<16}")
        print("  " + "─" * (width + 34))
        for line in statement.lines:
            label = ("  " * line.indent_level) + line.label
            print(f"  {label:<{width}} {line.current or '':<16} {line.prior or '':<16}")
    print()
    print(
        f"  Source: SEC EDGAR · Statement: {statement_type.label} · Extraction: {statement.source}"
    )
    if record.sec_url:
        print(f"  Original: {record.sec_url}")
    if statement.extraction_warnings:
        print(f"  {dim(statement.extraction_warnings[0])}")
