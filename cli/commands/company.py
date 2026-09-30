import math

from backend.app.cli import build_analysis_service
from cli.formatters import (
    bold,
    dim,
    fmt_dollar,
    fmt_net_income,
    fmt_pct,
    fmt_ratio,
    green,
    print_header,
    print_key_value,
    print_separator,
    red,
)


def register(subparsers):
    p = subparsers.add_parser(
        "company",
        help="Informacion basica de una empresa",
        description="Muestra nombre, precio y metricas principales de un ticker.",
    )
    p.add_argument("ticker", type=str, help="Ticker a consultar (ej: AAPL)")
    p.set_defaults(func=_run)


def _run(args):
    ticker = args.ticker.upper().strip()
    service = build_analysis_service()

    print_header(f"Informacion de {ticker}")

    try:
        name = service._market.get_company_name(ticker)
    except Exception:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
        name = None
    try:
        price = service._market.get_current_price(ticker)
    except Exception:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
        price = None
    try:
        mc = service._market.get_market_cap(ticker)
    except Exception:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
        mc = None

    print_key_value("Nombre", name or dim("No disponible"))
    print_key_value("Precio", fmt_dollar(price) if price else dim("No disponible"))
    print_key_value("Market Cap", fmt_dollar(mc) if mc else dim("No disponible"))

    try:
        result = service.analyze(ticker)
    except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
        print(f"\n  {red('ERROR:')} No se pudo analizar {ticker}: {e}")
        return

    if result is None:
        print(f"\n  {red('ERROR:')} Sin datos suficientes para {ticker}")
        return

    print()
    print(f"  {bold('Metricas fundamentales')}")
    dim_line = dim("─" * 60)
    print(f"  {dim_line}")

    metrics = [
        ("PER", result.get("per"), "fmt_ratio", 1),
        ("P/B", result.get("pb"), "fmt_ratio", 2),
        ("ROE", result.get("roe"), "fmt_pct", 1),
        ("ROIC", result.get("roic"), "fmt_pct", 1),
        ("Margen Operativo", result.get("operating_margin"), "fmt_pct", 1),
        ("Margen Neto", result.get("net_margin"), "fmt_pct", 1),
        ("FCF Yield", result.get("fcf_yield"), "fmt_pct", 1),
        ("EV/EBIT", result.get("ev_ebit"), "fmt_ratio", 1),
        (
            "D/E",
            result.get("debt_to_equity") if "debt_to_equity" in result else None,
            "fmt_ratio",
            2,
        ),
        ("Piotroski F-Score", result.get("piotroski_fscore"), "int", 0),
        ("Altman Z-Score", result.get("altman_zscore"), "fmt_ratio", 2),
        ("FCF Conversion", result.get("fcf_conversion"), "fmt_pct", 1),
        ("Net Debt/EBITDA", result.get("net_debt_to_ebitda"), "fmt_ratio", 2),
        ("Interest Coverage", result.get("interest_coverage"), "fmt_ratio", 1),
        ("Shareholder Yield", result.get("shareholder_yield"), "fmt_pct", 1),
        ("Croic", result.get("croic"), "fmt_pct", 1),
        ("DCF Value", result.get("dcf_value"), "fmt_dollar", 0),
        ("Score Compuesto", result.get("score"), "fmt_ratio", 4),
    ]

    for label, val, fmt_type, decimals in metrics:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            formatted = dim("N/A")
        elif fmt_type == "fmt_pct":
            formatted = fmt_pct(val, decimals)
        elif fmt_type == "fmt_dollar":
            formatted = fmt_dollar(val)
        elif fmt_type == "fmt_ratio":
            formatted = fmt_ratio(val, decimals)
        elif fmt_type == "int":
            formatted = str(int(val))
        else:
            formatted = str(val)

        if label == "ROE" and val is not None and val > 0.15:
            formatted = green(formatted)
        elif label == "ROE" and val is not None and val < 0.05:
            formatted = red(formatted)
        elif label == "PER" and val is not None and val < 15:
            formatted = green(formatted)
        elif label == "PER" and val is not None and val > 30:
            formatted = red(formatted)

        print_key_value(label, formatted)

    print()
    print_key_value("Revenue", fmt_dollar(result.get("revenue")) + " USD")
    print_key_value(
        "Net Income",
        fmt_net_income(result.get("net_income"), result.get("net_income_convention")),
    )
    print_key_value("Free Cash Flow", fmt_dollar(result.get("fcf")) + " USD")

    print_separator("-")
