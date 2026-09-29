#!/usr/bin/env python3
"""Compare financial data from Financial-DataBase with other providers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add the project root to the Python path so we can import backend modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os

from backend.app.cli import build_financial_repository
from backend.config.settings import get_sec_email
from backend.providers.edgar import EdgarProvider
from backend.providers.yahoo import YahooFinanceProvider


class _ProviderFinancials:
    """Simple wrapper to hold financial data for comparison."""
    def __init__(self):
        self.revenue: float | None = None
        self.net_income: float | None = None
        self.total_assets: float | None = None
        self.total_liabilities: float | None = None
        self.operating_cash_flow: float | None = None
        self.capital_expenditure: float | None = None  # positive value
        self.shareholders_equity: float | None = None
        self.diluted_eps: float | None = None
        self.free_cash_flow: float | None = None
        self.fiscal_year: int | None = None


def _extract_financials_from_yahoo(ticker: str) -> _ProviderFinancials | None:
    """Extract financials from Yahoo Finance provider."""
    try:
        yahoo = YahooFinanceProvider()
        income = yahoo.get_income_statement(ticker)
        balance = yahoo.get_balance_sheet(ticker)
        cash_flow = yahoo.get_cash_flow(ticker)
        shares_outstanding = yahoo.get_shares_outstanding(ticker)

        if not any([income, balance, cash_flow]):
            return None

        fin = _ProviderFinancials()
        if income:
            fin.revenue = float(income.revenue) if income.revenue is not None else None
            fin.net_income = float(income.net_income) if income.net_income is not None else None
        if balance:
            fin.total_assets = float(balance.total_assets) if balance.total_assets is not None else None
            fin.total_liabilities = float(balance.total_liabilities) if balance.total_liabilities is not None else None
            fin.shareholders_equity = float(balance.stockholders_equity) if balance.stockholders_equity is not None else None
        if cash_flow:
            fin.operating_cash_flow = float(cash_flow.operating_cash_flow) if cash_flow.operating_cash_flow is not None else None
            # Capital expenditure is often negative; we want positive for comparison
            capex = cash_flow.capital_expenditure
            if capex is not None:
                fin.capital_expenditure = abs(float(capex))
            fin.free_cash_flow = float(cash_flow.free_cash_flow) if cash_flow.free_cash_flow is not None else None
        # Calculate diluted EPS if possible
        if fin.net_income is not None and shares_outstanding is not None and shares_outstanding != 0:
            fin.diluted_eps = fin.net_income / float(shares_outstanding)
        # Attempt to get fiscal year (most recent)
        try:
            years = yahoo.get_fiscal_years(ticker)
            if years:
                fin.fiscal_year = int(years[0])
        except Exception:  # noqa: S110 — intentional try/except/pass (best-effort cleanup)
            pass
        return fin
    except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
        print(f"WARNING: Could not process data from Yahoo Finance for {ticker}: {e}")
        return None


def _extract_financials_from_edgar(ticker: str) -> _ProviderFinancials | None:
    """Extract financials from EDGAR provider."""
    try:
        edgar = EdgarProvider(
            email=get_sec_email(),
            name=os.getenv("SEC_NAME", "").strip() or "Value Investing",
        )
        income = edgar.get_income_statement(ticker)
        balance = edgar.get_balance_sheet(ticker)
        cash_flow = edgar.get_cash_flow(ticker)

        if not any([income, balance, cash_flow]):
            return None

        fin = _ProviderFinancials()
        if income:
            fin.revenue = float(income.revenue) if income.revenue is not None else None
            fin.net_income = float(income.net_income) if income.net_income is not None else None
        if balance:
            fin.total_assets = float(balance.total_assets) if balance.total_assets is not None else None
            fin.total_liabilities = float(balance.total_liabilities) if balance.total_liabilities is not None else None
            fin.shareholders_equity = float(balance.stockholders_equity) if balance.stockholders_equity is not None else None
        if cash_flow:
            fin.operating_cash_flow = float(cash_flow.operating_cash_flow) if cash_flow.operating_cash_flow is not None else None
            capex = cash_flow.capital_expenditure
            if capex is not None:
                fin.capital_expenditure = abs(float(capex))
            fin.free_cash_flow = float(cash_flow.free_cash_flow) if cash_flow.free_cash_flow is not None else None
        # Calculate diluted EPS if possible (EDGAR provider doesn't have shares_outstanding method)
        # We could try to get it from the balance sheet? Not available. Leave as None.
        # Attempt to get fiscal year (not directly available; we could try to infer from filings? skip)
        return fin
    except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
        print(f"WARNING: Could not process data from EDGAR for {ticker}: {e}")
        return None


def compare_financials(ticker: str, provider: str = "both") -> None:
    """Compare financial data for a ticker between Financial-DataBase and other providers.

    Args:
        ticker: Company ticker symbol
        provider: Which provider(s) to compare against Financial-DataBase ('yahoo', 'edgar', 'both')
    """
    print(f"\n{'='*60}")
    print(f"Comparing financial data for {ticker}")
    print(f"{'='*60}")

    # Get Financial-DataBase repository
    try:
        fd_repo = build_financial_repository()
        if not fd_repo.available():
            print(f"ERROR: Financial-DataBase repository not available for {ticker}")
            return
    except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
        print(f"ERROR: Could not initialize Financial-DataBase repository: {e}")
        return

    # Get latest financial data from Financial-DataBase
    try:
        years = fd_repo.list_years(ticker)
        if not years:
            print(f"WARNING: No financial data found in Financial-DataBase for {ticker}")
            fd_financials = None
        else:
            # Prefer the most recent completed fiscal year (with a period='FY'
            # record) over the potentially in-progress current year.
            target_year = getattr(fd_repo, 'get_latest_completed_fiscal_year', lambda t: None)(ticker)
            if target_year is not None:
                fd_financials = next(
                    (fy for fy in years if fy.fiscal_year == target_year),
                    years[0],
                )
            else:
                fd_financials = years[0]
    except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
        print(f"ERROR: Could not get financial data from Financial-DataBase for {ticker}: {e}")
        fd_financials = None

    # Get data from Yahoo Finance if requested
    yahoo_financials = None
    if provider in ("yahoo", "both"):
        yahoo_financials = _extract_financials_from_yahoo(ticker)

    # Get data from EDGAR if requested
    edgar_financials = None
    if provider in ("edgar", "both"):
        edgar_financials = _extract_financials_from_edgar(ticker)

    # Define fields to compare (fundamentals only — prices are never compared)
    fields_to_compare = [
        ('revenue', 'Revenue'),
        ('net_income', 'Net Income'),
        ('total_assets', 'Total Assets'),
        ('total_liabilities', 'Total Liabilities'),
        ('operating_cash_flow', 'Operating Cash Flow'),
        ('capital_expenditure', 'Capital Expenditures'),
    ]

    # Prepare data for comparison
    data_sources = []
    source_names = []

    if fd_financials:
        data_sources.append(fd_financials)
        source_names.append('Financial-DataBase')

    if yahoo_financials:
        data_sources.append(yahoo_financials)
        source_names.append('Yahoo Finance')

    if edgar_financials:
        data_sources.append(edgar_financials)
        source_names.append('EDGAR')

    if not data_sources:
        print(f"ERROR: No financial data available from any source for {ticker}")
        return

    # Print header
    print(f"\nFiscal Year: {getattr(fd_financials, 'fiscal_year', 'N/A') if fd_financials else 'N/A'}")
    print("-" * 60)

    # Print comparison table
    header = f"{'Field':<25}"
    for name in source_names:
        header += f"{name:>15}"
    header += f"{'Diff (%)':>12}"
    print(header)
    print("-" * len(header))

    # Compare each field
    for field_attr, field_name in fields_to_compare:
        values = []
        for financials in data_sources:
            value = getattr(financials, field_attr, None)
            values.append(value)

        # Format values for display
        formatted_values = []
        for value in values:
            if value is None:
                formatted_values.append("N/A")
            else:
                # Format large numbers
                if abs(value) >= 1e9:
                    formatted_values.append(f"{value/1e9:.2f}B")
                elif abs(value) >= 1e6:
                    formatted_values.append(f"{value/1e6:.2f}M")
                elif abs(value) >= 1e3:
                    formatted_values.append(f"{value/1e3:.2f}K")
                else:
                    formatted_values.append(f"{value:.2f}")

        # Calculate percentage difference between first two sources (if both have values)
        diff_pct = "N/A"
        if len(values) >= 2 and values[0] is not None and values[1] is not None:
            if values[1] != 0:  # Avoid division by zero
                diff = ((values[0] - values[1]) / abs(values[1])) * 100
                diff_pct = f"{diff:+.2f}%"
            else:
                diff_pct = "N/A (div by 0)"

        # Print row
        row = f"{field_name:<25}"
        for val in formatted_values:
            row += f"{val:>15}"
        row += f"{diff_pct:>12}"
        print(row)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY:")
    sources_with_data = [name for name, data in zip(source_names, data_sources) if data is not None]
    print(f"  Sources with data: {', '.join(sources_with_data)}")

    # Flag significant discrepancies
    if len(data_sources) >= 2:
        print("\n  Significant discrepancies (>5%):")
        found_discrepancy = False
        for i, (field_attr, field_name) in enumerate(fields_to_compare):
            values = [getattr(ds, field_attr, None) for ds in data_sources[:2]]  # Compare first two sources
            if len(values) == 2 and values[0] is not None and values[1] is not None and values[1] != 0:
                diff_pct = abs((values[0] - values[1]) / values[1]) * 100
                if diff_pct > 5.0:
                    print(f"    {field_name}: {diff_pct:.2f}% difference")
                    found_discrepancy = True
        if not found_discrepancy:
            print("    No significant discrepancies found (>5%)")


def main():
    """Main function to run the comparison script."""
    parser = argparse.ArgumentParser(
        description="Compare financial data from Financial-DataBase with other providers"
    )
    parser.add_argument(
        "tickers",
        nargs="+",
        help="Ticker(s) to compare (e.g: AAPL or AAPL MSFT KO)",
    )
    parser.add_argument(
        "--provider",
        choices=["yahoo", "edgar", "both"],
        default="both",
        help="Which provider(s) to compare against Financial-DataBase (default: both)",
    )

    args = parser.parse_args()

    # Process each ticker
    for raw_ticker in args.tickers:
        ticker = raw_ticker.upper().strip()
        try:
            compare_financials(ticker, args.provider)
        except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
            print(f"ERROR processing {ticker}: {e}", file=sys.stderr)
            continue

    print("\nComparison complete.")


if __name__ == "__main__":
    main()