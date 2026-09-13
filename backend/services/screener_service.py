import time
from typing import Optional

from backend.analytics.service import CompanyAnalysisService
from backend.domain.interfaces.data_loader import DataLoader
from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.interfaces.provider import MarketDataProvider
from backend.domain.value_objects.filter_criteria import FilterCriteria
from backend.domain.value_objects.screener_result import ScreenerRow
from backend.providers.tickers import TICKERS
from backend.services.price_service import PriceService


class StockScreenerService:
    def __init__(
        self,
        repository: FinancialRepository,
        market_provider: MarketDataProvider,
        loader: Optional[DataLoader] = None,
        price_service: Optional[PriceService] = None,
    ):
        self._analysis = CompanyAnalysisService(
            repository, market_provider, loader=loader
        )
        self._market = market_provider
        self._repository = repository
        self._price_service = price_service or PriceService()

    def screen(
        self,
        tickers: Optional[list[str]] = None,
        filters: Optional[list[FilterCriteria]] = None,
        top_n: Optional[int] = None,
        progress_callback=None,
    ) -> list[ScreenerRow]:
        if tickers is None:
            tickers = TICKERS
        filters = filters or []

        results: list[ScreenerRow] = []
        total = len(tickers)

        for idx, ticker in enumerate(tickers):
            if progress_callback:
                progress_callback(idx + 1, total, ticker)

            try:
                row = self._analyze_ticker(ticker)
                if row is None:
                    continue
                if self._passes_filters(row, filters):
                    results.append(row)
            except Exception:
                continue

            if idx < total - 1:
                time.sleep(0.15)

        results.sort(key=lambda r: r.score or 0, reverse=True)
        if top_n is not None:
            results = results[:top_n]
        return results

    def search(self, query: str) -> list[str]:
        q = query.upper().strip()
        matches = []
        for t in TICKERS:
            if q in t:
                matches.append(t)
            else:
                try:
                    name = self._market.get_company_name(t)
                    if name and query.lower() in name.lower():
                        if t not in matches:
                            matches.append(t)
                except Exception:
                    continue
        return matches[:20]

    def _analyze_ticker(self, ticker: str) -> Optional[ScreenerRow]:
        d = self._analysis.analyze(ticker)
        if d is None:
            return None

        # Real-time price (never persisted). Resilient: returns None when Yahoo
        # rate-limits or fails, and the row is still built with fundamentals.
        price = None
        try:
            price = self._price_service.get_current_price(ticker)
        except Exception:  # noqa: BLE001
            price = None

        name = None
        try:
            name = self._market.get_company_name(ticker)
        except Exception:  # noqa: BLE001
            name = None

        # If the market provider failed to produce price-derived metrics, try
        # to compute them from the real-time price + fundamentals (repository).
        enriched = self._enrich_with_real_time_price(d, ticker, price)

        return ScreenerRow(
            ticker=ticker,
            name=name,
            price=price,
            market_cap=enriched.get("market_cap"),
            per=enriched.get("per"),
            pb=enriched.get("pb"),
            roe=enriched.get("roe"),
            roic=enriched.get("roic"),
            operating_margin=enriched.get("operating_margin"),
            net_margin=enriched.get("net_margin"),
            fcf_yield=enriched.get("fcf_yield"),
            ev_ebit=enriched.get("ev_ebit"),
            debt_to_equity=enriched.get("debt_to_equity"),
            revenue_growth=enriched.get("revenue_growth"),
            fcf=enriched.get("fcf"),
            score=enriched.get("score"),
            extra=d,
        )

    def _enrich_with_real_time_price(
        self, d: dict, ticker: str, price: Optional[float]
    ) -> dict:
        """Fill in price-dependent valuation metrics from real-time prices.

        Keeps whatever the analysis layer already computed and only adds the
        missing pieces (P/E, FCF yield, EV/EBIT) when a real-time price and the
        fundamentals are available. Fails gracefully: on any error the original
        metrics are preserved.
        """
        try:
            if price is None:
                return d

            shares = d.get("shares_outstanding")
            if not shares:
                try:
                    shares = self._price_service.get_shares_outstanding(ticker)
                except Exception:  # noqa: BLE001
                    shares = None
            if shares is None or shares == 0:
                return d

            market_cap = price * float(shares)
            if d.get("market_cap") is None:
                d["market_cap"] = market_cap

            net_income = d.get("net_income")
            if d.get("per") is None and net_income and net_income != 0:
                d["per"] = market_cap / net_income

            fcf = d.get("fcf")
            if d.get("fcf_yield") is None and fcf is not None and market_cap != 0:
                d["fcf_yield"] = fcf / market_cap

            if d.get("ev_ebit") is None:
                ebit = d.get("ebit")
                debt = d.get("total_debt")
                cash = d.get("cash_and_equivalents")
                if ebit and ebit != 0:
                    ev = market_cap + (debt or 0) - (cash or 0)
                    d["ev_ebit"] = ev / ebit
        except Exception:  # noqa: BLE001
            pass

        return d

    @staticmethod
    def _passes_filters(row: ScreenerRow, filters: list[FilterCriteria]) -> bool:
        for f in filters:
            val = _get_field(row, f.field)
            if not f.matches(val):
                return False
        return True


def _get_field(row: ScreenerRow, field: str):
    if hasattr(row, field):
        return getattr(row, field)
    return row.extra.get(field)