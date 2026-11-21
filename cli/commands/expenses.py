"""`expenses` — XBRL-disclosed expense lines for one company."""

from __future__ import annotations

import json

from backend.app.cli import add_demo_argument
from backend.services.expense_service import ExpenseService
from cli.formatters import dim, print_header, print_table, red, yellow


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "expenses",
        help="Disaggregated expense lines (marketing, R&D, occupancy...)",
        description=(
            "Reads the XBRL expense tags available in Financial-DataBase. "
            "Lines without a tag are shown as 'not disclosed', never as 0."
        ),
    )
    p.add_argument("ticker", help="Ticker (e.g. KO)")
    p.add_argument(
        "--year", type=int, default=None, help="Fiscal year (default: latest)"
    )
    p.add_argument("--json", action="store_true", help="Print the raw payload")
    add_demo_argument(p)
    p.set_defaults(func=_run)


def _money(value: float | None) -> str:
    if value is None:
        return "not disclosed"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    return f"${value:,.0f}"


def _run(args) -> None:
    ticker = args.ticker.upper().strip()
    try:
        report = ExpenseService().build(ticker, getattr(args, "year", None))
    except Exception as exc:  # noqa: BLE001 — boundary catch-all (DB/network)
        print(red(f"ERROR: could not read expenses for {ticker}: {exc}"))
        return
    if report is None:
        print(red(f"No fundamentals or expense facts for {ticker}."))
        return

    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return

    print_header(f"Expense lines · {report.ticker} · FY{report.fiscal_year}")
    if report.name and report.name != report.ticker:
        print(f"  {report.name}")
    print(
        dim(
            f"  Currency: {report.currency}"
            + (f" → USD (FX {report.fx_rate:.4f})" if report.fx_rate else "")
        )
    )
    if report.note:
        print(dim(f"  {report.note}"))
    if not report.applicable:
        print(yellow(f"  {report.note or 'Not comparable for this company type.'}"))

    print_table(
        [("Line item", 0), ("Value", 1), ("Source / status", 0)],
        [
            [
                line.label,
                _money(line.value) if line.is_disclosed else dim("not disclosed"),
                line.source if line.is_disclosed else line.reason,
            ]
            for line in report.lines
        ],
    )
    disclosed = sum(1 for line in report.lines if line.is_disclosed)
    print()
    print(f"  Disclosed: {disclosed}/{len(report.lines)} lines")
    print(
        dim(
            "  XBRL has no universal 'electricity' or 'marketing' tag; missing "
            "lines are not estimated."
        )
    )
