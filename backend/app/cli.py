import argparse
import logging
import os
import sys
import time
from typing import Optional

from dotenv import load_dotenv

from backend.analytics.interpretation import print_analysis
from backend.analytics.service import CompanyAnalysisService
from backend.config.settings import get_output_dir
from backend.domain.entities.company import Company
from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.interfaces.provider import MarketDataProvider
from backend.domain.value_objects.filter_criteria import FilterCriteria, FilterOperator
from backend.domain.value_objects.financials_normalized import ProviderName
from backend.providers.tickers import TICKERS
from backend.repositories.json_financial_repository import JsonFinancialRepository
from backend.repositories.financial_database_repository import FinancialDatabaseRepository
from backend.screener.screener_service import ScreenerService
from backend.services.data_pipeline_service import DataPipelineService
from backend.services.price_service import get_price_service
from backend.services.screener_service import StockScreenerService
from backend.utils.input import get_tickers
from cli.formatters import dim, green, red, yellow

load_dotenv()

# The SEC contact is personal data: it is read from the environment (the
# git-ignored .env) and never hardcoded. Empty means "not configured", which
# build_data_pipeline turns into a clear error at the point of use.
sec_email = os.getenv("SEC_EMAIL", "").strip()
sec_name = os.getenv("SEC_NAME", "").strip() or "Value Investing"

logger = logging.getLogger("backend.app")


def build_financial_repository() -> FinancialRepository:
    # Try Financial-DataBase repository first
    try:
        financial_db_repo = FinancialDatabaseRepository()
        if financial_db_repo.available():
            logger.info("Using Financial-DataBase financial repository")
            return financial_db_repo
    except Exception as e:
        logger.warning(f"Financial-DataBase repository unavailable: {e}")

    # Fall back to existing PostgreSQL repository
    # (imported lazily — SQLAlchemy is heavy and is only needed on this path)
    from backend.repositories.financial_repository import SqlAlchemyFinancialRepository

    repository = SqlAlchemyFinancialRepository()
    if repository.available():
        logger.info("Using PostgreSQL financial repository")
        return repository

    # Finally fall back to JSON storage
    logger.warning("PostgreSQL unavailable — falling back to JSON storage")
    return JsonFinancialRepository(os.getenv("NORMALIZED_DATA_DIR", "data/normalized"))


def build_data_pipeline() -> DataPipelineService:
    # Providers are imported lazily here (not at module import) because
    # edgartools and yfinance are heavy (~1.6s combined) and are only needed
    # for live-fetch commands, never for FDB-backed reads.
    from backend.adapters.database.repositories.company_repository import (
        CompanyRepository,
    )
    from backend.providers.edgar import EdgarProvider
    from backend.providers.yahoo import YahooFinanceProvider
    from backend.repositories.financial_repository import SqlAlchemyFinancialRepository

    yahoo = YahooFinanceProvider()
    if sec_email:
        edgar = EdgarProvider(email=sec_email, name=sec_name)
    else:
        # No contact configured: the live EDGAR fallback is disabled rather
        # than sending unattributed requests (the SEC answers 403), and the
        # command keeps working on the Financial-DataBase data, which is where
        # the fundamentals come from anyway. Live EDGAR fetching needs
        # SEC_EMAIL in .env.
        logger.warning(
            "SEC_EMAIL is not configured: the live EDGAR fallback is disabled "
            "(set SEC_EMAIL in .env, copy .env.example, to enable it)"
        )
        edgar = None
    repository = build_financial_repository()

    def _save_company(ticker: str) -> None:
        CompanyRepository().save(Company(ticker=ticker))

    return DataPipelineService(
        repository=repository,
        primary=yahoo,
        fallback=edgar,
        market=yahoo,
        company_saver=(
            _save_company
            if isinstance(repository, SqlAlchemyFinancialRepository)
            else None
        ),
        report_source=(
            ProviderName.EDGAR
            if isinstance(repository, FinancialDatabaseRepository)
            else None
        ),
    )


def build_analysis_service(
    market_provider: Optional[MarketDataProvider] = None,
    analysis_cache=None,
) -> CompanyAnalysisService:
    """CompanyAnalysisService reading from Financial-DataBase.

    ``market_provider`` defaults to the live Yahoo provider. The daily
    workflow passes a SnapshotMarketProvider (prefetched quote snapshots) so
    batch analysis runs with zero per-ticker network calls.

    ``analysis_cache`` may be an :class:`AnalysisCache` (used as-is), ``False``
    to disable it, or ``None`` to build the default cache when the repository
    supports fingerprints and ``ANALYSIS_CACHE`` is not disabled.
    """
    if market_provider is None:
        from backend.providers.yahoo import YahooFinanceProvider

        market_provider = YahooFinanceProvider()
    repository = build_financial_repository()
    cache = analysis_cache
    if analysis_cache is None:
        from backend.services.analysis_cache import AnalysisCache

        cache = AnalysisCache(
            repository=repository,
            enabled=os.environ.get("ANALYSIS_CACHE", "1").lower()
            not in ("0", "false", "no"),
        )
    # The per-year DB lookups (shares outstanding, fiscal-year-end) live in the
    # same entry, so the repository must know about the cache too — otherwise
    # only the fundamentals read would be cached and every valuation/validation
    # command would keep re-querying facts that have not changed.
    attach = getattr(repository, "attach_analysis_cache", None)
    if callable(attach):
        attach(cache)
    return CompanyAnalysisService(
        repository=repository,
        market_provider=market_provider,
        loader=build_data_pipeline(),
        history_cache=cache,
    )


def build_screener_service() -> StockScreenerService:
    from backend.providers.yahoo import YahooFinanceProvider

    yahoo = YahooFinanceProvider()
    return StockScreenerService(
        repository=build_financial_repository(),
        market_provider=yahoo,
        loader=build_data_pipeline(),
        price_service=get_price_service(),
    )


def build_investment_screener(
    universe: Optional[list[str]] = None, no_prices: bool = False
) -> ScreenerService:
    """Screener over intelligence outputs, enriched with real-time prices."""
    enrich = _company_enrichment()
    if universe is None:
        universe = _tracked_tickers()
    return ScreenerService(
        analyzer=build_analysis_service().analyze,
        universe=universe,
        enrich=enrich,
        price_service=get_price_service(),
        no_prices=no_prices,
    )


def add_refresh_arguments(parser) -> None:
    """Add the on-demand SEC refresh flags to an analysis parser.

    --refresh / --no-refresh are mutually exclusive; --freshness-hours
    overrides the configured freshness threshold (default 168h).
    """
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--refresh",
        action="store_true",
        help="Forzar sincronizacion SEC de los tickers analizados (ignora antiguedad)",
    )
    group.add_argument(
        "--no-refresh",
        action="store_true",
        help="No sincronizar datos SEC antes del analisis (usa los datos existentes)",
    )
    parser.add_argument(
        "--freshness-hours",
        type=int,
        default=None,
        metavar="N",
        help="Antiguedad maxima (horas) para considerar datos frescos (default: 168)",
    )


def refresh_analysis_inputs(
    tickers: list[str],
    args=None,
    *,
    fetch_prices: bool = True,
    explicit: bool = True,
):
    """Ensure the analyzed tickers are fresh and warm real-time prices.

    Runs a freshness check and, for each stale company, a targeted
    ``sec sync <CIK>`` — only for the tickers being analyzed; the full
    universe is never synced here. Real-time prices are fetched through
    PriceService and returned in the RefreshResult (never persisted).

    Args:
        tickers: exact ticker list that will be analyzed.
        args: argparse namespace with --refresh / --no-refresh /
            --freshness-hours (optional; missing attrs default off).
        fetch_prices: when False, skip the price fetch (e.g. --no-prices).
        explicit: True when the tickers were provided by the user (targeted
            run). Universe-wide runs (default screener/momentum/alerts over
            the tracked universe) never auto-sync; pass --refresh to force.

    Returns:
        RefreshResult with .refreshed/.skipped/.failed and .prices.
    """
    from backend.services.refresh_service import RefreshService, load_refresh_config

    config = load_refresh_config()
    force = bool(getattr(args, "refresh", False)) if args else False
    no_refresh = bool(getattr(args, "no_refresh", False)) if args else False
    freshness_hours = getattr(args, "freshness_hours", None)
    if freshness_hours is not None:
        try:
            freshness_hours = int(freshness_hours)
        except (TypeError, ValueError):
            freshness_hours = None

    skip = None  # None => let the config decide (skip_refresh_flag/auto_refresh)
    if no_refresh or (not explicit and not force):
        # --no-refresh, or a universe-wide run without --refresh: never
        # auto-sync the whole universe; per-CIK refresh is for explicit runs.
        skip = True

    service = RefreshService(config=config)
    result = service.ensure_fresh_and_prices(
        list(tickers),
        force=force,
        max_age_hours=freshness_hours,
        skip_refresh=skip,
        fetch_prices=fetch_prices,
    )
    _print_refresh_summary(
        result, universe_wide=(not explicit and not force and not no_refresh)
    )
    return result


def _print_refresh_summary(result, *, universe_wide: bool = False) -> None:
    """One compact line describing the freshness/prices step."""
    sync_failures = [r for r in result.failed if "CIK mapping" not in r[1]]
    pieces = []
    if result.refreshed:
        n = len(result.refreshed)
        pieces.append(
            green(f"{n} sincronizado{'s' if n > 1 else ''} con SEC")
        )
    if result.skipped:
        pieces.append(dim(f"{len(result.skipped)} sin tocar"))
    if sync_failures:
        pieces.append(red(f"{len(sync_failures)} con fallo"))
    if getattr(result, "sec_skipped_reason", None):
        pieces.append(yellow("SEC no disponible — refresh SEC omitido"))
    if universe_wide:
        pieces.append(
            dim("universo amplio: refresh acotado (usa --refresh para forzar)")
        )
    if not pieces:
        return
    print("  " + " · ".join(pieces))


def load_universe(path: Optional[str] = None) -> Optional[list[str]]:
    """Read a optional universe file (one ticker per line, '#' comments).

    Returns None when the file does not exist so callers can fall back to
    their default universe (e.g. the static ticker list).
    """
    target = path or os.getenv("UNIVERSE_PATH", "config/universe.txt")
    try:
        with open(target, encoding="utf-8") as handle:
            tickers = [
                line.strip().upper()
                for line in handle
                if line.strip() and not line.lstrip().startswith("#")
            ]
    except OSError:
        return None
    return tickers or None


def build_universe(tickers: Optional[list[str]] = None) -> list[str]:
    """Tick universe: explicit tickers, or every tracked company in storage."""
    if tickers:
        return [t.strip().upper() for t in tickers]
    return _tracked_tickers()


def _tracked_tickers() -> list[str]:
    """Tickers tracked in storage, falling back to the static universe if the
    database is unavailable so the CLI keeps working."""
    try:
        return [c.ticker for c in CompanyRepository().list_all()] or TICKERS
    except Exception:  # noqa: BLE001 — database down must not kill the CLI
        logger.warning("storage unavailable — falling back to static ticker list")
        return TICKERS


def cmd_historical_valuation(args):
    """Show historical valuation ratios (P/E and FCF yield) for tickers."""
    from backend.services.historical_valuation_service import HistoricalValuationService

    service = HistoricalValuationService()
    tickers = get_tickers()

    if not tickers:
        print("Error: No tickers provided")
        return

    for ticker in tickers:
        print(f"\nHistorical Valuation Ratios for {ticker}")
        print("=" * 50)
        table_output = service.format_valuation_table(ticker)
        print(table_output)


def build_financial_repository() -> FinancialRepository:
    # Try Financial-DataBase repository first
    try:
        financial_db_repo = FinancialDatabaseRepository()
        if financial_db_repo.available():
            logger.info("Using Financial-DataBase financial repository")
            return financial_db_repo
    except Exception as e:
        logger.warning(f"Financial-DataBase repository unavailable: {e}")

    # Fall back to existing PostgreSQL repository
    # (imported lazily — SQLAlchemy is heavy and is only needed on this path)
    from backend.repositories.financial_repository import SqlAlchemyFinancialRepository

    repository = SqlAlchemyFinancialRepository()
    if repository.available():
        logger.info("Using PostgreSQL financial repository")
        return repository

    # Finally fall back to JSON storage
    logger.warning("PostgreSQL unavailable — falling back to JSON storage")
    return JsonFinancialRepository(os.getenv("NORMALIZED_DATA_DIR", "data/normalized"))


def build_portfolio_service():
    """Portfolio tracking wired to the analytics layer for live refresh."""
    from backend.portfolio.portfolio_repository import JsonPortfolioRepository
    from backend.portfolio.portfolio_service import PortfolioService

    return PortfolioService(
        repository=JsonPortfolioRepository(
            os.getenv("PORTFOLIO_PATH", "data/portfolio.json")
        ),
        analyzer=build_analysis_service().analyze,
    )


def build_watchlist_service():
    """Watchlist monitoring wired to the analytics layer for enrichment."""
    from backend.watchlist.watchlist_repository import JsonWatchlistRepository
    from backend.watchlist.watchlist_service import WatchlistService

    return WatchlistService(
        repository=JsonWatchlistRepository(
            os.getenv("WATCHLIST_PATH", "data/watchlist.json")
        ),
        analyzer=build_analysis_service().analyze,
    )


def _company_enrichment():
    def enrich(ticker: str, item: dict) -> dict:
        try:
            company = CompanyRepository().find_by_ticker(ticker)
            if company:
                item["sector"] = company.sector
                item["industry"] = company.industry
        except Exception as e:  # noqa: BLE001
            logger.warning("company metadata unavailable for %s: %s", ticker, e)
        return item

    return enrich


def cmd_analyze(args):
    service = build_analysis_service()
    tickers = get_tickers()
    results = []

    print("\nAnalizando...\n")
    for t in tickers:
        print(f"-> {t}")
        try:
            result = service.analyze(t)
            if result:
                results.append(result)
                print_analysis(result)
            else:
                print(f"  Sin datos suficientes para {t}")
        except Exception as e:
            print(f"  Error analizando {t}: {e}")
            continue

    if not results:
        print("\nNo se pudo extraer datos para ningun ticker.")
        return

    import pandas as pd

    df = pd.DataFrame(results).sort_values("score", ascending=False)
    output_dir = get_output_dir()
    os.makedirs(output_dir, exist_ok=True)
    csv_filename = os.path.join(output_dir, "analisis_completo.csv")
    df.to_csv(csv_filename, index=False)
    print(f"\nResultados guardados en {csv_filename}")
    print("\n" + "=" * 80)
    print("RANKING FINAL (por score)")
    print("=" * 80)
    for i, row in df.iterrows():
        ticker = row["ticker"]
        score = row["score"]
        if score is not None:
            print(f"{i+1}. {ticker} : {score:.4f}")
        else:
            print(f"{i+1}. {ticker} : sin score")
    print(f"\nTop pick: {df.iloc[0]['ticker']}")


def cmd_screener(args):
    service = build_screener_service()

    filters = []
    if args.filter:
        for f in args.filter:
            try:
                parts = f.split()
                field = parts[0]
                op = parts[1]
                if op == "between":
                    low, high = float(parts[2]), float(parts[3])
                    filters.append(FilterCriteria.between(field, low, high))
                elif op == "<":
                    filters.append(FilterCriteria.lt(field, float(parts[2])))
                elif op == ">":
                    filters.append(FilterCriteria.gt(field, float(parts[2])))
                elif op == "==":
                    filters.append(FilterCriteria.eq(field, parts[2]))
                elif op == "<=":
                    filters.append(
                        FilterCriteria(
                            field=field,
                            operator=FilterOperator.LTE,
                            value=float(parts[2]),
                        )
                    )
                elif op == ">=":
                    filters.append(
                        FilterCriteria(
                            field=field,
                            operator=FilterOperator.GTE,
                            value=float(parts[2]),
                        )
                    )
            except (IndexError, ValueError) as e:
                print(f"  Error en filtro '{f}': {e}")
                return

    tickers = args.tickers.split(",") if args.tickers else None

    print(
        f"\nEjecutando screener sobre {len(tickers) if tickers else '~150'} tickers..."
    )
    print(
        "Filtros: "
        + (
            " ".join(f"{f.field} {f.operator.value} {f.value}" for f in filters)
            or "(ninguno)"
        )
    )
    print()

    def progress(current, total, ticker):
        pct = int(current / total * 100)
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        sys.stdout.write(f"\r  [{bar}] {current}/{total} ({pct}%) {ticker}   ")
        sys.stdout.flush()

    start = time.time()
    results = service.screen(
        tickers=tickers,
        filters=filters,
        top_n=args.top,
        progress_callback=progress,
    )
    elapsed = time.time() - start

    print(f"\n\nResultados: {len(results)} empresas en {elapsed:.1f}s\n")

    if not results:
        print("  Ninguna empresa cumple los filtros.")
        return

    header = " ".join(
        [
            f"{'Ticker':>6}",
            f"{'Nombre':<28}",
            f"{'Price':>8}",
            f"{'PER':>8}",
            f"{'P/B':>8}",
            f"{'ROE':>7}",
            f"{'FCF':>13}",
            f"{'Score':>7}",
        ]
    )
    print(header)
    print("-" * len(header))
    for r in results:
        name_trunc = (r.name or "")[:27]
        price_str = f"{r.price:.2f}" if r.price else "N/A"
        per_str = f"{r.per:.1f}" if r.per else "N/A"
        pb_str = f"{r.pb:.2f}" if r.pb else "N/A"
        roe_str = f"{r.roe:.1%}" if r.roe else "N/A"
        fcf_str = f"{r.fcf:,.0f}" if r.fcf else "N/A"
        score_str = f"{r.score:.4f}" if r.score else "N/A"
        print(
            f"{r.ticker:>6} {name_trunc:<28} {price_str:>8} {per_str:>8} "
            f"{pb_str:>8} {roe_str:>7} {fcf_str:>13} {score_str:>7}"
        )

    if args.save:
        import pandas as pd

        path = os.path.join(get_output_dir(), "screener_resultados.csv")
        os.makedirs(get_output_dir(), exist_ok=True)
        rows = [
            {
                "ticker": r.ticker,
                "name": r.name,
                "price": r.price,
                "per": r.per,
                "pb": r.pb,
                "roe": r.roe,
                "roic": r.roic,
                "op_margin": r.operating_margin,
                "net_margin": r.net_margin,
                "fcf_yield": r.fcf_yield,
                "ev_ebit": r.ev_ebit,
                "debt_to_equity": r.debt_to_equity,
                "fcf": r.fcf,
                "score": r.score,
            }
            for r in results
        ]
        pd.DataFrame(rows).to_csv(path, index=False)
        print(f"\nResultados guardados en {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Value Investing - Backend de Analisis Fundamental"
    )
    sub = parser.add_subparsers(dest="command", help="Comandos disponibles")

    p_analyze = sub.add_parser(
        "analyze", help="Analizar uno o varios tickers (modo clasico)"
    )
    p_analyze.set_defaults(func=cmd_analyze)

    p_screener = sub.add_parser("screener", help="Stock screener con filtros")
    p_screener.add_argument(
        "--tickers", type=str, default=None, help="Tickers separados por coma"
    )
    p_screener.add_argument("--top", type=int, default=30, help="Maximo de resultados")
    p_screener.add_argument(
        "--save", action="store_true", help="Guardar resultados en CSV"
    )
    p_screener.add_argument(
        "--filter",
        action="append",
        default=[],
        help='Filtros: "per < 15", "pb between 1 1.5", "roe > 0.15", "fcf > 1000000"',
    )
    p_screener.set_defaults(func=cmd_screener)

    # Historical valuation command
    p_hist = sub.add_parser(
        "historical-valuation", help="Show historical valuation ratios (P/E and FCF yield)"
    )
    p_hist.set_defaults(func=cmd_historical_valuation)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
