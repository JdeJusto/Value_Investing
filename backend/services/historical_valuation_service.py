"""Service for calculating historical valuation ratios like P/E and FCF yield.

The service combines fundamental data from FinancialDatabaseRepository with
realtime prices fetched through PriceService. Prices are NEVER persisted —
they are retrieved on demand from Yahoo Finance (with a short in-memory cache).
"""

from __future__ import annotations

import logging
from typing import Any

from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)
from backend.services.price_service import PriceService

logger = logging.getLogger(__name__)

#: Share counts above this magnitude are suspicious enough to cross-check the
#: adjacent fiscal years before using them in EPS/P-E. COP FY2011 (1.375e12
#: vs ~1.375e9) and BTI FY2019 (2.456e15 vs ~2.456e9) are the canonical cases.
_SUSPICIOUS_SHARES = 1e11


def format_pe_for_display(pe: float | None, net_income: float | None) -> str:
    """Format a P/E for a table: exact unless earnings are near zero.

    The JSON/API keeps the numeric value; only the human table uses ``n.m.``.
    """
    if pe is None:
        return "N/A"
    if net_income is not None and abs(net_income) < 1e6:
        return "n.m."
    return f"{pe:.2f}"


class HistoricalValuationService:
    """Service for calculating historical valuation ratios."""

    # Core fields any usable fiscal year must populate. A fiscal-year bucket
    # that only picked up stray non-income facts (e.g. an in-progress year fed
    # by an 8-K — NetFeeAmt/TtlFeeAmt/...) has none of them and must not
    # produce a phantom "latest year" row in the valuation table. Mirrors
    # FinancialDatabaseRepository._row_is_empty so the two layers agree.
    _CORE_FIELDS = ("revenue", "net_income", "total_assets", "shares_outstanding")

    @staticmethod
    def _row_is_empty(row) -> bool:
        return all(
            getattr(row, field) is None
            for field in HistoricalValuationService._CORE_FIELDS
        )

    def __init__(
        self,
        repository: FinancialRepository | None = None,
        price_service: PriceService | None = None,
    ):
        """Initialize the historical valuation service.

        Args:
            repository: Financial repository with fundamental data. If None,
                       creates a FinancialDatabaseRepository instance.
            price_service: Real-time price source. If None, creates a
                          PriceService instance.
        """
        self._repository = repository or FinancialDatabaseRepository()
        self._price_service = price_service or PriceService()

    def get_historical_pe_ratios(self, ticker: str) -> list[dict[str, Any]]:
        """Get historical P/E ratios for a ticker.

        P/E = price_at_fiscal_year_end / EPS, where EPS is derived from
        net_income / shares_outstanding when not directly available.

        Args:
            ticker: Company ticker symbol

        Returns:
            List of dictionaries containing fiscal year, price, EPS, and P/E ratio
        """
        ratios = self.get_historical_valuation_summary(ticker)
        # Return only the P/E ratio related fields
        pe_ratios = []
        for ratio in ratios:
            pe_ratios.append(
                {
                    "fiscal_year": ratio["fiscal_year"],
                    "price": ratio["price"],
                    "eps": ratio["eps"],
                    "pe_ratio": ratio["pe_ratio"],
                }
            )
        return pe_ratios

    def get_historical_fcf_yields(self, ticker: str) -> list[dict[str, Any]]:
        """Get historical FCF yields for a ticker.

        FCF yield = free_cash_flow / market_cap, where
        market_cap = price_at_fiscal_year_end * shares_outstanding.

        Args:
            ticker: Company ticker symbol

        Returns:
            List of dictionaries containing fiscal year, price, shares, market cap,
            FCF, and FCF yield
        """
        ratios = self.get_historical_valuation_summary(ticker)
        # Return only the FCF yield related fields
        fcf_yields = []
        for ratio in ratios:
            fcf_yields.append(
                {
                    "fiscal_year": ratio["fiscal_year"],
                    "price": ratio["price"],
                    "shares_outstanding": ratio["shares_outstanding"],
                    "market_cap": ratio["market_cap"],
                    "free_cash_flow": ratio["free_cash_flow"],
                    "fcf_yield": ratio["fcf_yield"],
                }
            )
        return fcf_yields

    def get_historical_valuation_summary(self, ticker: str) -> list[dict[str, Any]]:
        """Calculate historical valuation ratios for a ticker.

        Uses fundamentals from the financial repository and real-time prices
        from PriceService. Rows where price data is unavailable are still
        returned so callers can render "N/A" gracefully.

        Args:
            ticker: Company ticker symbol

        Returns:
            List of dictionaries containing all valuation ratio data,
            sorted by fiscal year descending
        """
        try:
            # Skip all-empty rows (a stray/in-progress fiscal-year bucket with
            # no revenue, income, assets or shares): it is not a year the
            # valuation can use and must not surface as the "latest year".
            financials_by_year = {
                row.fiscal_year: row
                for row in self._repository.list_years(ticker)
                if not self._row_is_empty(row)
            }
        except Exception:  # noqa: BLE001
            return []

        ratios: list[dict[str, Any]] = []
        for year in sorted(financials_by_year.keys(), reverse=True):
            financials = financials_by_year[year]

            shares = self._safe_shares(ticker, year)
            fiscal_year_end = self._safe_fiscal_year_end(ticker, year)
            price = self._price_service.get_price_at_fiscal_year_end(
                ticker, year, fiscal_year_end
            )

            eps = None
            pe_ratio = None
            market_cap = None
            fcf_yield = None

            # Yahoo Finance prices are split-adjusted; as-reported shares are
            # not. Bring the reported share count onto the same (current)
            # basis so per-share metrics stay consistent across stock splits.
            split_adjustment = 1.0
            if fiscal_year_end is not None:
                split_adjustment = self._price_service.get_split_adjustment(
                    ticker, fiscal_year_end
                )

            if shares and shares != 0:
                adjusted_shares = shares * split_adjustment
                if financials.net_income is not None:
                    eps = (
                        financials.net_income / adjusted_shares
                        if adjusted_shares
                        else None
                    )

                if price is not None:
                    market_cap = price * adjusted_shares
                    if eps not in (None, 0):
                        pe_ratio = price / eps
                    # FCF yield uses direct FreeCashFlow when available,
                    # falling back to operating cash flow minus capex (a
                    # common derivation since the raw figure is sometimes
                    # missing from the database).
                    fcf = financials.free_cash_flow
                    if fcf is None and (
                        financials.operating_cash_flow is not None
                        and financials.capital_expenditure is not None
                    ):
                        fcf = (
                            financials.operating_cash_flow
                            - financials.capital_expenditure
                        )
                    if fcf is not None and market_cap != 0:
                        fcf_yield = fcf / market_cap

            ratios.append(
                {
                    "fiscal_year": year,
                    "price": price,
                    "eps": eps,
                    "pe_ratio": pe_ratio,
                    "fcf_yield": fcf_yield,
                    "market_cap": market_cap,
                    "shares_outstanding": shares,
                    "shares_adjusted": shares * split_adjustment if shares else None,
                    "split_adjustment": split_adjustment,
                    "net_income": financials.net_income,
                    "free_cash_flow": fcf if market_cap else financials.free_cash_flow,
                }
            )

        return ratios

    def _safe_shares(self, ticker: str, fiscal_year: int) -> float | None:
        shares = self._raw_shares(ticker, fiscal_year)
        if shares is None:
            return None
        return self._shares_with_neighbor_sanity(ticker, fiscal_year, shares)

    def _raw_shares(self, ticker: str, fiscal_year: int) -> float | None:
        """Repository share count without the neighbor sanity check."""
        try:
            shares = self._repository.get_shares_outstanding(ticker, fiscal_year)
            return float(shares) if shares is not None else None
        except Exception:  # noqa: BLE001
            return None

    def _shares_with_neighbor_sanity(
        self, ticker: str, fiscal_year: int, shares: float
    ) -> float:
        """Reject share counts that are 100x+ away from both neighbors.

        Only values above ``_SUSPICIOUS_SHARES`` are cross-checked, so normal
        companies do not pay for two extra repository reads. The fallback is
        the neighbor median, not a fabricated number: COP/BTI have the correct
        count in the adjacent fiscal years.
        """
        if shares <= 0 or shares < _SUSPICIOUS_SHARES:
            return shares
        neighbors = [
            value
            for value in (
                self._raw_shares(ticker, fiscal_year - 1),
                self._raw_shares(ticker, fiscal_year + 1),
            )
            if value is not None and value > 0
        ]
        if not neighbors:
            return shares
        median = sorted(neighbors)[len(neighbors) // 2]
        if median <= 0:
            return shares
        ratio = shares / median
        if ratio > 100 or ratio < 0.01:
            logger.warning(
                "shares outlier %s FY%s: %.0f vs neighbor median %.0f "
                "(%.1fx); using neighbor",
                ticker,
                fiscal_year,
                shares,
                median,
                ratio,
            )
            return median
        return shares

    def _safe_fiscal_year_end(self, ticker: str, fiscal_year: int):
        """Best-known fiscal year end date, or None to let PriceService fall back."""
        try:
            if hasattr(self._repository, "get_fiscal_year_end_date"):
                return self._repository.get_fiscal_year_end_date(ticker, fiscal_year)
        except Exception:  # noqa: BLE001
            return None
        return None

    def format_valuation_table(self, ticker: str) -> str:
        """Format historical valuation ratios as a readable table.

        Columns: fiscal_year | price | eps | pe_ratio | fcf_yield
        Missing values are rendered as "N/A".
        """
        ratios = self.get_historical_valuation_summary(ticker)

        if not ratios:
            return f"No valuation data available for {ticker}"

        header = f"{'fiscal_year':>10} | {'price':>8} | {'eps':>8} | {'pe_ratio':>10} | {'fcf_yield':>10}"
        separator = "-" * len(header)

        rows = []
        for ratio in ratios:
            year = ratio["fiscal_year"]
            price = f"{ratio['price']:.2f}" if ratio["price"] is not None else "N/A"
            eps = f"{ratio['eps']:.2f}" if ratio["eps"] is not None else "N/A"
            pe_ratio = format_pe_for_display(ratio["pe_ratio"], ratio.get("net_income"))
            fcf_yield = (
                f"{ratio['fcf_yield']:.2%}" if ratio["fcf_yield"] is not None else "N/A"
            )

            row = (
                f"{year:>10} | {price:>8} | {eps:>8} | {pe_ratio:>10} | {fcf_yield:>10}"
            )
            rows.append(row)

        return f"{header}\n{separator}\n" + "\n".join(rows)


def _get_service() -> HistoricalValuationService:
    """Get or create a historical valuation service instance.

    Returns:
        HistoricalValuationService instance
    """
    return HistoricalValuationService()


if __name__ == "__main__":
    service = HistoricalValuationService()
    print(service.format_valuation_table("AAPL"))
