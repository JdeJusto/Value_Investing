from backend.app.cli import build_financial_repository
from backend.domain.services import days_since_loaded, is_stale, needs_refresh
from cli.formatters import bold, dim, green, print_header, print_key_value, red


def register(subparsers):
    p = subparsers.add_parser(
        "data-status",
        help="Estado de calidad, frescura y consistencia de los datos",
        description=(
            "Muestra por ticker el origen de cada anio fiscal, la cobertura, "
            "la calidad, la procedencia de los datos y si requieren refresco."
        ),
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="+",
        help="Ticker(s) a inspeccionar (ej: AAPL o AAPL MSFT GOOGL)",
    )
    p.set_defaults(func=_run)


def _status_labels(row, available: bool) -> str:
    if is_stale(row):
        return red("DESACTUALIZADO")
    if not available and row.is_complete:
        return dim("no usado (origen alternativo)")
    return green("frescos")


def _run(args):
    repository = build_financial_repository()

    for raw_ticker in args.tickers:
        ticker = raw_ticker.upper().strip()
        print_header(f"Estado de datos: {ticker}")

        rows = repository.list_all(ticker)
        if not rows:
            print(
                f"  {red('Sin datos persistidos.')} Usa 'main.py load-data {ticker}'."
            )
            continue

        selected = {r.fiscal_year: r for r in repository.get_best_available(ticker)}

        print(f"  {bold('Origen por anio fiscal')}")
        for row in sorted(rows, key=lambda r: r.fiscal_year, reverse=True):
            source = row.source.value.upper()
            quality = (
                f"{row.data_quality_score:.2f}"
                if row.data_quality_score is not None
                else dim("N/A")
            )
            completeness = (
                f"{row.data_completeness:.0%}"
                if row.data_completeness is not None
                else dim("N/A")
            )
            derived = (
                f" (+derivados: {', '.join(row.derived_metrics)})"
                if row.derived_metrics
                else ""
            )
            print_key_value(
                f"{row.fiscal_year} [{source}]",
                f"calidad {quality} · cobertura {completeness}{derived} · "
                f"{_status_labels(row, row.fiscal_year in selected)}",
            )

        selection = selected.values()
        if selection:
            sources = sorted({row.source for row in selection})
            data_source = "MIXED" if len(sources) > 1 else sources[0].value.upper()
            print_key_value("Seleccion analisis", data_source)
            for row in selection:
                days = days_since_loaded(row)
                print_key_value(
                    f"  {row.fiscal_year}",
                    f"{row.source.value.upper()} · actualizado hace "
                    f"{days if days is not None else 'N/A'} dias",
                )
            print_key_value(
                "Refresco necesario", "si" if needs_refresh(list(selection)) else "no"
            )

        print()
