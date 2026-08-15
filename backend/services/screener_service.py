import time
from typing import Optional

from backend.analytics.service import CompanyAnalysisService
from backend.domain.interfaces.data_loader import DataLoader
from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.interfaces.provider import MarketDataProvider
from backend.domain.value_objects.filter_criteria import FilterCriteria
from backend.domain.value_objects.screener_result import ScreenerRow
from backend.providers.tickers import TICKERS


class StockScreenerService:
    def __init__(
        self,
        repository: FinancialRepository,
        market_provider: MarketDataProvider,
        loader: Optional[DataLoader] = None,
    ):
        self._analysis = CompanyAnalysisService(
            repository, market_provider, loader=loader
        )
        self._market = market_provider

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

        name = self._market.get_company_name(ticker)
        price = self._market.get_current_price(ticker)

        return ScreenerRow(
            ticker=ticker,
            name=name,
            price=price,
            market_cap=d.get("market_cap"),
            per=d.get("per"),
            pb=d.get("pb"),
            roe=d.get("roe"),
            roic=d.get("roic"),
            operating_margin=d.get("operating_margin"),
            net_margin=d.get("net_margin"),
            fcf_yield=d.get("fcf_yield"),
            ev_ebit=d.get("ev_ebit"),
            debt_to_equity=d.get("debt_to_equity"),
            revenue_growth=d.get("revenue_growth"),
            fcf=d.get("fcf"),
            score=d.get("score"),
            extra=d,
        )

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
