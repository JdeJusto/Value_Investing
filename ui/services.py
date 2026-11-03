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


#: The screener reads the newest N fiscal years: enough for every
#: methodology's trend window without paying for the full ~16-year archive.
SCREENER_HISTORY_YEARS = 10


@st.cache_data(ttl=3600)
def load_filings(ticker: str):
    """Cached official filings for one ticker (read-only, never downloaded)."""
    from backend.services.filing_service import FilingService

    return FilingService().list_filings(ticker)


@st.cache_data(ttl=3600)
def load_fundamentals(ticker: str):
    """Cached fundamentals for one ticker (DB read only, nothing persisted)."""
    rows = build_financial_repository().get_best_available(
        ticker, max_years=SCREENER_HISTORY_YEARS
    )
    return [row for row in rows if row is not None]


@st.cache_data(ttl=900)
def load_quote(ticker: str) -> dict:
    """Cached price/market-cap snapshot; in-memory only, never persisted."""
    service = get_price_service()
    try:
        price = service.get_current_price(ticker)
    except Exception:  # noqa: BLE001 — a missing quote must not break the page
        price = None
    try:
        market_cap = service.get_market_cap(ticker)
    except Exception:  # noqa: BLE001 — a missing market cap is not an error
        market_cap = None
    return {"price": price, "market_cap": market_cap}


@st.cache_data(ttl=3600, show_spinner=False)
def load_scorecard(ticker: str, period: str = "FY") -> dict | None:
    """Cached scorecard payload for one ticker (``Scorecard.to_dict()``).

    Presentation only: the scorecard service is built from the same
    repository and price service the rest of the analysis page uses, and
    the frozen dataclass is converted to a plain dict so Streamlit's cacher
    can serialize it. ``None`` means no fundamentals (the page shows its
    usual warning); a service error propagates so the tab can report it.
    """
    from backend.services.scorecard_service import ScorecardService

    service = ScorecardService(
        repository=build_financial_repository(),
        price_service=get_price_service(),
    )
    card = service.build(ticker, period)
    return None if card is None else card.to_dict()


@st.cache_data(ttl=3600, show_spinner=False)
def load_scorecard_charts(ticker: str) -> dict | None:
    """Cached chart series for the Scorecard tab (``ScorecardCharts.to_dict``).

    Presentation only: the series come from ``ScorecardChartService``, which
    reuses the same repository, calculators and DCF as the analysis page.
    Prices are read through the price service (in-memory cache) and are never
    persisted. ``None`` means no fundamentals.
    """
    from backend.services.scorecard_charts_service import ScorecardChartService

    service = ScorecardChartService(
        repository=build_financial_repository(),
        price_service=get_price_service(),
    )
    charts = service.build(ticker)
    return None if charts is None else charts.to_dict()


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
    except Exception:  # noqa: BLE001 — no history is not a crash
        return []


@st.cache_data(ttl=60)
def load_portfolio(path: str):
    """Read-only load of the portfolio JSON; nothing is written."""
    from backend.portfolio.portfolio_repository import JsonPortfolioRepository

    try:
        return JsonPortfolioRepository(path).load()
    except Exception:  # noqa: BLE001 — a broken file must not crash the page
        return None


@st.cache_data(ttl=3600)
def load_sector_map(tickers: tuple[str, ...]) -> dict:
    """Sector per ticker from the fundamentals repository (None when unknown)."""
    repository = build_financial_repository()
    sectors: dict[str, str | None] = {}
    for ticker in tickers:
        try:
            rows = [row for row in repository.get_best_available(ticker) if row]
        except Exception:  # noqa: BLE001 — an unknown sector is not an error
            rows = []
        sectors[ticker] = rows[0].sector if rows else None
    return sectors


def _fdb_url() -> str:
    import os

    return os.environ.get(
        "FINANCIAL_DATABASE_URL",
        "postgresql://financial:test@localhost:5432/financial_database",
    )


@st.cache_data(ttl=3600)
def load_sector_options() -> list[str]:
    """Distinct sectors in Financial-DataBase (screener filter options)."""
    import psycopg2

    try:
        with psycopg2.connect(_fdb_url()) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT sector FROM companies "
                "WHERE sector IS NOT NULL ORDER BY sector"
            )
            return [row[0] for row in cur.fetchall()]
    except Exception:  # noqa: BLE001 — DB down: no sector options, not a crash
        return []


@st.cache_data(ttl=3600)
def load_sector_map_bulk(tickers: tuple[str, ...]) -> dict[str, str | None]:
    """Sector per ticker in ONE query (screener pre-filter)."""
    if not tickers:
        return {}
    import psycopg2

    found: dict[str, str | None] = {}
    try:
        with psycopg2.connect(_fdb_url()) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT cl.ticker, c.sector
                FROM company_listings cl
                JOIN companies c ON c.id = cl.company_id
                WHERE UPPER(cl.ticker) = ANY(%s) AND cl.is_active
                """,
                ([ticker.upper() for ticker in tickers],),
            )
            found = {row[0].upper(): row[1] for row in cur.fetchall()}
    except Exception:  # noqa: BLE001 — DB down: no sectors, filtering degrades
        found = {}
    return {ticker.upper(): found.get(ticker.upper()) for ticker in tickers}
