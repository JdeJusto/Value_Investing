"""Historical valuation command for showing P/E and FCF yield history."""

from __future__ import annotations

import sys

from backend.app.cli import (
    add_demo_argument,
    add_refresh_arguments,
    build_financial_repository,
    refresh_analysis_inputs,
)
from backend.services.historical_valuation_service import HistoricalValuationService
from cli.formatters import (
    dim,
    print_header,
    print_key_value,
    red,
    yellow,
)


def register(subparsers):
    """Register the historical-valuation command."""
    p = subparsers.add_parser(
        "historical-valuation",
        help="Show historical valuation ratios (P/E and FCF yield)",
        description=(
            "Shows historical P/E ratios and FCF yield for a ticker "
            "using price data from Financial-DataBase."
        ),
    )
    p.add_argument(
        "tickers",
        nargs="+",
        help="Ticker(s) to show historical valuation for (e.g: AAPL or AAPL MSFT)",
    )
    add_refresh_arguments(p)
    add_demo_argument(p)
    p.set_defaults(func=_run)


def _run(args):
    """Run the historical-valuation command."""
    print(f"DEBUG: historical_valuation _run called with args: {args}", file=sys.stderr)
    service = HistoricalValuationService()
    repo = build_financial_repository()
    tickers = [t.upper().strip() for t in args.tickers]
    print(f"DEBUG: tickers: {tickers}", file=sys.stderr)
    refresh_analysis_inputs(tickers, args)

    if not repo.available():
        print(f"{red('ERROR:')} Financial-DataBase repository not available")
        return

    for ticker in tickers:
        print_header(f"Historical Valuation Ratios for {ticker}")

        # Check if we have any financial data
        if not repo.has_data(ticker):
            print(f"  {red('No financial data for')} {ticker}")
            continue

        # Get historical valuation ratios
        ratios = service.get_historical_valuation_summary(ticker)
        print(f"DEBUG: got {len(ratios)} ratios for {ticker}", file=sys.stderr)

        if not ratios:
            print(f"  {yellow('No valuation data available for')} {ticker}")
            print(
                f"  {dim('This may be due to missing price data in Financial-DataBase')}"
            )
            continue

        # Print table
        table_output = service.format_valuation_table(ticker)
        print(table_output)

        # Show latest values if available
        if ratios:
            latest = ratios[0]  # Most recent year first
            print()
            print_key_value("Latest fiscal year", str(latest["fiscal_year"]))
            print_key_value(
                "Closing price",
                f"{latest['price']:.2f}" if latest["price"] is not None else "N/A",
            )
            print_key_value(
                "EPS",
                f"{latest['eps']:.2f}" if latest["eps"] is not None else "N/A",
            )
            print_key_value(
                "P/E Ratio",
                f"{latest['pe_ratio']:.2f}"
                if latest["pe_ratio"] is not None
                else "N/A",
            )
            print_key_value(
                "FCF Yield",
                f"{latest['fcf_yield']:.2%}"
                if latest["fcf_yield"] is not None
                else "N/A",
            )
