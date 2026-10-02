"""`filings` — official SEC filings for a ticker, with EDGAR links."""

from __future__ import annotations

import webbrowser
from datetime import date

from backend.app.cli import add_demo_argument
from cli.formatters import dim, print_header, red


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
        help="Print the raw URLs instead of clickable links",
    )
    p.add_argument("--limit", type=int, default=40, help="Max rows (default 40)")
    p.add_argument(
        "--open", action="store_true", help="Open the newest match in the browser"
    )
    add_demo_argument(p)
    p.set_defaults(func=_run)


def _hyperlink(url: str | None) -> str:
    """OSC 8 clickable link (modern terminals); an em dash when missing."""
    if not url:
        return dim("—")
    return f"\033]8;;{url}\033\\open\033]8;;\033\\"


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
            print(red(f"Fecha inválida: {args.since} (usa YYYY-MM-DD)"))
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
        print(red(f"ERROR: no se pudieron leer los filings de {ticker}: {exc}"))
        return

    print_header(f"Filings — {ticker}" + (f" ({name})" if name else ""))
    if not records:
        print(
            "  No hay filings que coincidan con los filtros. Prueba --all o "
            "un rango de fechas más amplio."
        )
        return

    print(
        f"  {'Form':<7} {'Filed':<12} {'Period':<12} {'FY':<6} {'Accession':<22} Link"
    )
    print("  " + "─" * 74)
    for record in records:
        link = record.sec_url or ""
        shown = link if args.urls else _hyperlink(link)
        period = record.period_of_report.isoformat() if record.period_of_report else "—"
        fiscal_year = (
            str(record.effective_fiscal_year) if record.effective_fiscal_year else "—"
        )
        print(
            f"  {record.form_type:<7} {record.filing_date.isoformat():<12} "
            f"{period:<12} {fiscal_year:<6} {record.accession_number:<22} {shown}"
        )

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

    if args.open:
        target = records[0].sec_url
        if target:
            webbrowser.open(target)
            print(
                f"  Abriendo {records[0].form_type} "
                f"{records[0].filing_date.isoformat()} en el navegador…"
            )
