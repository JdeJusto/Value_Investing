from backend.app.cli import build_data_pipeline
from backend.services.data_pipeline_service import PipelineError
from cli.formatters import bold, dim, green, print_header, print_key_value, red


def register(subparsers):
    p = subparsers.add_parser(
        "load-data",
        help="Descarga, normaliza y persiste datos financieros historicos",
        description=(
            "Ejecuta el pipeline completo (fetch -> normalizar -> almacenar) "
            "para uno o varios tickers."
        ),
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="+",
        help="Ticker(s) a cargar (ej: AAPL o AAPL MSFT GOOGL)",
    )
    p.add_argument(
        "--years",
        type=int,
        default=None,
        help="Numero de anios fiscales a cargar (default: 10)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Re-descargar y sobrescribir datos aunque ya existan en el almacenamiento"
        ),
    )
    p.set_defaults(func=_run)


def _run(args):
    pipeline = build_data_pipeline()

    for raw_ticker in args.tickers:
        ticker = raw_ticker.upper().strip()
        print_header(f"Cargando datos historicos: {ticker}")

        try:
            result = pipeline.load_ticker(ticker, years=args.years, force=args.force)
        except PipelineError as e:
            print(f"  {red('ERROR:')} {e}")
            continue
        except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
            print(f"  {red('ERROR:')} Fallo inesperado cargando {ticker}: {e}")
            continue

        source_label = (
            result.source.value
            if hasattr(result.source, "value")
            else str(result.source)
        )
        if result.cached:
            print(
                f"  {dim('Ya estaba en el almacenamiento (cache) — usa --force para re-descargar')}"
            )
        print_key_value("Origen", source_label)
        print_key_value("Anios cargados", f"{result.years_loaded}")

        metrics = [
            "revenue",
            "net_income",
            "free_cash_flow",
            "total_assets",
            "total_liabilities",
        ]
        if result.statements:
            print(f"  {bold('Ultimo anio fiscal')}")
            last = result.statements[0]
            print_key_value("Fiscal Year", str(last.fiscal_year))
            for field in metrics:
                value = getattr(last, field, None)
                formatted = (
                    f"{value:,.0f}" if isinstance(value, (int, float)) else dim("N/A")
                )
                print_key_value(field.replace("_", " ").title(), formatted)

        if result.errors:
            print(f"  {red('Errores:')} {'; '.join(result.errors)}")

    print(
        "\n"
        + green("Listo.")
        + " Los datos normalizados quedaron persistidos para analisis posteriores."
    )
