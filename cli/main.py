import argparse
import logging
import sys

logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)


def main():
    print("DEBUG: main() called", file=sys.stderr)
    print("DEBUG: sys.argv = {}".format(sys.argv), file=sys.stderr)
    print("DEBUG: About to create parser", file=sys.stderr)
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Value Investing Platform — Analisis fundamental desde la terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  main.py screener --per-max 15 --roe-min 12 --top 10\n"
            '  main.py screener --search "apple"\n'
            "  main.py company AAPL\n"
            "  main.py analyze AAPL MSFT GOOGL\n"
            "  main.py buffett-analysis AAPL\n"
            "  main.py load-data AAPL\n"
            "  main.py load-data AAPL --years 15 --force\n"
            "  main.py data-status AAPL\n"
            "  main.py screener --tickers AAPL,MSFT --pb-min 1 --pb-max 5\n"
            "  main.py screener --filter moat=STRONG min_score=80\n"
            "  main.py opportunities\n"
            "  main.py anomalies AAPL\n"
            "  main.py momentum\n"
            '  main.py portfolio add AAPL 10 180 --thesis "moat fuerte"\n'
            "  main.py portfolio view\n"
            "  main.py portfolio performance\n"
            "  main.py backtest --strategy momentum --top 3\n"
            "  main.py backtest --strategy buffett --prices precios.csv\n"
            "  main.py alerts\n"
            '  main.py watchlist add AAPL --note "pendiente de entry"\n'
            "  main.py watchlist list\n"
            "  main.py debug\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", title="Comandos")

    from cli.commands import (
        alerts,
        analyze,
        anomalies,
        backtest,
        buffett_analysis,
        company,
        data_status,
        debug,
        historical_valuation,
        load_data,
        momentum,
        opportunities,
        portfolio,
        screener,
        sql_analysis,
        watchlist,
    )

    screener.register(sub)
    company.register(sub)
    analyze.register(sub)
    buffett_analysis.register(sub)
    historical_valuation.register(sub)
    load_data.register(sub)
    data_status.register(sub)
    opportunities.register(sub)
    anomalies.register(sub)
    momentum.register(sub)
    portfolio.register(sub)
    backtest.register(sub)
    alerts.register(sub)
    watchlist.register(sub)
    debug.register(sub)
    sql_analysis.register(sub)

    if len(sys.argv) == 1:
        parser.print_help()
        return

    args = parser.parse_args()
    args.func(args)
