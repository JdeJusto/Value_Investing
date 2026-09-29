import streamlit as st

from backend.analytics.service import CompanyAnalysisService
from backend.app.cli import build_data_pipeline, build_financial_repository
from backend.providers.yahoo import YahooFinanceProvider
from backend.services.price_service import get_price_service
from backend.services.screener_service import StockScreenerService


@st.cache_resource
def get_market_provider():
    return YahooFinanceProvider()


@st.cache_resource
def get_analysis_service():
    return CompanyAnalysisService(
        repository=build_financial_repository(),
        market_provider=get_market_provider(),
        loader=build_data_pipeline(),
    )


@st.cache_resource
def get_screener_service():
    return StockScreenerService(
        repository=build_financial_repository(),
        market_provider=get_market_provider(),
        loader=build_data_pipeline(),
    )


@st.cache_data(ttl=3600)
def load_fundamentals(ticker: str):
    """Cached fundamentals for one ticker (DB read only, nothing persisted)."""
    rows = build_financial_repository().get_best_available(ticker)
    return [row for row in rows if row is not None]


@st.cache_data(ttl=900)
def load_quote(ticker: str) -> dict:
    """Cached price/market-cap snapshot; in-memory only, never persisted."""
    service = get_price_service()
    try:
        price = service.get_current_price(ticker)
    except Exception:
        price = None
    try:
        market_cap = service.get_market_cap(ticker)
    except Exception:
        market_cap = None
    return {"price": price, "market_cap": market_cap}


@st.cache_data(ttl=3600)
def load_historical_valuation(ticker: str) -> list:
    """Cached P/E and FCF-yield history for the valuation chart."""
    from backend.services.historical_valuation_service import (
        HistoricalValuationService,
    )

    service = HistoricalValuationService(
        repository=build_financial_repository(),
        price_service=get_price_service(),
    )
    try:
        return service.get_historical_valuation_summary(ticker)
    except Exception:
        return []


@st.cache_data(ttl=60)
def load_portfolio(path: str):
    """Read-only load of the portfolio JSON; nothing is written."""
    from backend.portfolio.portfolio_repository import JsonPortfolioRepository

    try:
        return JsonPortfolioRepository(path).load()
    except Exception:
        return None


@st.cache_data(ttl=3600)
def load_sector_map(tickers: tuple[str, ...]) -> dict:
    """Sector per ticker from the fundamentals repository (None when unknown)."""
    repository = build_financial_repository()
    sectors: dict[str, str | None] = {}
    for ticker in tickers:
        try:
            rows = [row for row in repository.get_best_available(ticker) if row]
        except Exception:
            rows = []
        sectors[ticker] = rows[0].sector if rows else None
    return sectors
