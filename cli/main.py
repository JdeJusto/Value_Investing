import argparse
import sys


def main():
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
            "  main.py load-data AAPL\n"
            "  main.py load-data AAPL --years 15 --force\n"
            "  main.py screener --tickers AAPL,MSFT --pb-min 1 --pb-max 5\n"
            "  main.py debug\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", title="Comandos")

    from cli.commands import screener, company, analyze, load_data, debug

    screener.register(sub)
    company.register(sub)
    analyze.register(sub)
    load_data.register(sub)
    debug.register(sub)

    if len(sys.argv) == 1:
        parser.print_help()
        return

    args = parser.parse_args()
    args.func(args)
