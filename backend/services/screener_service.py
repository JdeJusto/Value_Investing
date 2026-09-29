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
        loader: DataLoader | None = None,
        price_service: PriceService | None = None,
    ):
        self._analysis = CompanyAnalysisService(
            repository, market_provider, loader=loader
        )
        self._market = market_provider
        self._repository = repository
        self._loader = loader
        self._price_service = price_service or PriceService()

    def screen(
        self,
        tickers: list[str] | None = None,
        filters: list[FilterCriteria] | None = None,
        top_n: int | None = None,
        progress_callback=None,
        no_prices: bool = False,
    ) -> list[ScreenerRow]:
        if tickers is None:
            tickers = TICKERS
        filters = filters or []
        tickers = [t.upper() for t in tickers if t]

        # Pool every per-ticker Yahoo .info call into ONE parallel snapshot
        # pass (PriceService.get_market_snapshots), then serve the sequential
        # analysis loop from memory via SnapshotMarketProvider — zero per-ticker
        # network round trips. Prices/shares are warmed into the in-memory
        # cache and never persisted; everything degrades gracefully when the
        # snapshot fetch fails (live provider remains in place).
        if not no_prices and self._price_service is not None:
            try:
                from backend.providers.snapshot import SnapshotMarketProvider

                snapshots = self._price_service.get_market_snapshots(
                    tickers, batch_size=20, delay=0.1, workers=6
                )
                # Only a real dict (a dict subclass triggers the swap; Mock
                # return values from unit tests keep the injected analysis).
                if isinstance(snapshots, dict):
                    self._market = SnapshotMarketProvider(snapshots)
                    self._analysis = CompanyAnalysisService(
                        self._repository, self._market, loader=self._loader
                    )
            except Exception:
                pass

        results: list[ScreenerRow] = []
        total = len(tickers)

        for idx, ticker in enumerate(tickers):
            if progress_callback:
                progress_callback(idx + 1, total, ticker)

            try:
                row = self._analyze_ticker(ticker, no_prices=no_prices)
                if row is None:
                    continue
                if self._passes_filters(row, filters):
                    results.append(row)
            except Exception:
                continue

            # With snapshots prefetched the loop is CPU/DB-bound; the pacing
            # sleep only matters on the exceptional live-provider path.
            if idx < total - 1:
                time.sleep(0.02)

        results.sort(key=lambda r: r.score or 0, reverse=True)
        if top_n is not None:
            results = results[:top_n]
        return results

    def search(self, query: str) -> list[str]:
        q = query.upper().strip()
        matches = []
        tickers = list(TICKERS)
        # Prefer the repository's name metadata (a local DB read — no
        # network), so `screener --search` stays fast over the whole universe.
        # Only when the repository has no name lookup do we fall back to a
        # single parallel quote-snapshot pass for the names.
        repo_name = getattr(self._repository, "get_company_name", None)
        snapshots: dict = {}
        if repo_name is None and self._price_service is not None:
            try:
                snapshots = self._price_service.get_market_snapshots(
                    tickers, batch_size=25, delay=0.1, workers=6
                )
            except Exception:
                snapshots = {}
        for t in tickers:
            if len(matches) >= 20:
                break
            if q in t:
                matches.append(t)
                continue
            if repo_name is not None:
                try:
                    name = repo_name(t)
                except Exception:
                    name = None
            else:
                snap = snapshots.get(t) or {}
                name = snap.get("longName") or snap.get("shortName")
                if not name and not snapshots:
                    try:
                        name = self._market.get_company_name(t)
                    except Exception:
                        name = None
            if name and query.lower() in name.lower():
                matches.append(t)
        return matches[:20]

    def _analyze_ticker(
        self, ticker: str, no_prices: bool = False
    ) -> ScreenerRow | None:
        d = self._analysis.analyze(ticker, no_prices=no_prices)
        if d is None:
            return None

        # Real-time price (never persisted). Resilient: returns None when Yahoo
        # rate-limits or fails, and the row is still built with fundamentals.
        # With no_prices the PriceService is never called.
        price = None
        if not no_prices:
            try:
                price = self._price_service.get_current_price(ticker)
            except Exception:
                price = None

        name = None
        try:
            name = self._market.get_company_name(ticker)
        except Exception:
            name = None

        # If the market provider failed to produce price-derived metrics, try
        # to compute them from the real-time price + fundamentals (repository).
        enriched = (
            self._enrich_with_real_time_price(d, ticker, price)
            if not no_prices
            else d
        )

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
        self, d: dict, ticker: str, price: float | None
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
                except Exception:
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
        except Exception:
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