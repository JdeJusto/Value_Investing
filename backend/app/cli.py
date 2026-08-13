import argparse
import logging
import os
import sys
import time

from dotenv import load_dotenv
import pandas as pd
from backend.analytics.interpretation import print_analysis
from backend.analytics.service import CompanyAnalysisService
from backend.config.settings import get_output_dir
from backend.adapters.database.repositories.company_repository import CompanyRepository
from backend.domain.entities.company import Company
from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.value_objects.filter_criteria import FilterCriteria, FilterOperator
from backend.providers.edgar import EdgarProvider
from backend.providers.yahoo import YahooFinanceProvider
from backend.repositories.financial_repository import SqlAlchemyFinancialRepository
from backend.repositories.json_financial_repository import JsonFinancialRepository
from backend.screener.screener_service import ScreenerService
from backend.services.data_pipeline_service import DataPipelineService
from backend.services.screener_service import StockScreenerService
from backend.utils.input import get_tickers

load_dotenv()

sec_email = os.getenv("SEC_EMAIL", "jaimedejusto@gmail.com")
sec_name = os.getenv("SEC_NAME", "Jaime")

logger = logging.getLogger("backend.app")


def build_financial_repository() -> FinancialRepository:
    repository = SqlAlchemyFinancialRepository()
    if repository.available():
        logger.info("Using PostgreSQL financial repository")
        return repository
    logger.warning("PostgreSQL unavailable — falling back to JSON storage")
    return JsonFinancialRepository(os.getenv("NORMALIZED_DATA_DIR", "data/normalized"))


def build_data_pipeline() -> DataPipelineService:
    yahoo = YahooFinanceProvider()
    edgar = EdgarProvider(email=sec_email, name=sec_name)
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
    )


def build_analysis_service() -> CompanyAnalysisService:
    yahoo = YahooFinanceProvider()
    return CompanyAnalysisService(
        repository=build_financial_repository(),
        market_provider=yahoo,
        loader=build_data_pipeline(),
    )


def build_screener_service() -> StockScreenerService:
    yahoo = YahooFinanceProvider()
    return StockScreenerService(
        repository=build_financial_repository(),
        market_provider=yahoo,
        loader=build_data_pipeline(),
    )


def build_investment_screener(universe: Optional[list[str]] = None) -> ScreenerService:
    """Screener over intelligence outputs, without direct provider access."""
    enrich = _company_enrichment()
    if universe is None:
        universe = [c.ticker for c in CompanyRepository().list_all()]
    return ScreenerService(
        analyzer=build_analysis_service().analyze,
        universe=universe,
        enrich=enrich,
    )


def build_universe(tickers: Optional[list[str]] = None) -> list[str]:
    """Tick universe: explicit tickers, or every tracked company in storage."""
    if tickers:
        return [t.strip().upper() for t in tickers]
    return [c.ticker for c in CompanyRepository().list_all()]


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


def _company_enrichment():
    def enrich(ticker: str, item: dict) -> dict:
        company = CompanyRepository().find_by_ticker(ticker)
        if company:
            item["sector"] = company.sector
            item["industry"] = company.industry
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
        f"Filtros: {[str(f.field) + ' ' + f.operator.value + ' ' + str(f.value) for f in filters] or '(ninguno)'}"
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

    header = f"{'Ticker':>6} {'Nombre':<28} {'Price':>8} {'PER':>8} {'P/B':>8} {'ROE':>7} {'FCF':>13} {'Score':>7}"
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
            f"{r.ticker:>6} {name_trunc:<28} {price_str:>8} {per_str:>8} {pb_str:>8} {roe_str:>7} {fcf_str:>13} {score_str:>7}"
        )

    if args.save:
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

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
