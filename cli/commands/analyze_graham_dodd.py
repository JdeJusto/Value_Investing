"""`analyze-graham-dodd` — run the Graham & Dodd methodology on one company."""

from __future__ import annotations

from backend.app.cli import add_demo_argument, add_refresh_arguments
from cli.formatters import (
    confidence_color,
    dim,
    print_header,
    print_key_value,
    print_section,
    red,
    verdict_color,
)


def register(subparsers):
    p = subparsers.add_parser(
        "analyze-graham-dodd",
        help="Run the Graham & Dodd deep-value screen on one company",
        description=(
            "Evaluates the Graham & Dodd rules for deep value: NWC test, "
            "fixed-charge coverage, earnings stability, balance sheet strength, "
            "and margin of safety."
        ),
    )
    p.add_argument("ticker", help="Ticker to evaluate (e.g. AAPL)")
    add_refresh_arguments(p)
    add_demo_argument(p)
    p.set_defaults(func=_run)


def _run(args):
    from backend.app.cli import build_financial_repository, refresh_analysis_inputs
    from backend.methodologies.registry import discover, registry
    from backend.services.price_service import get_price_service
    from cli.commands.preflight import require_known_tickers

    discover()
    require_known_tickers([args.ticker])
    refresh_analysis_inputs([args.ticker], args)
    methodology = registry.get("graham_dodd")
    if methodology is None:
        print("Error: graham_dodd methodology not registered")
        return

    repo = build_financial_repository()
    rows = repo.get_best_available(args.ticker)
    if not rows:
        print(f"No fundamentals found for {args.ticker}")
        return

    prices = get_price_service()
    result = methodology.evaluate(args.ticker, rows, prices)

    print_header(f"Graham & Dodd analysis — {args.ticker}")
    print_key_value("Verdict", verdict_color(result.verdict.value))
    print_key_value("Score", f"{result.score:.2f}" if result.score is not None else "—")
    print_key_value("Confidence", confidence_color(result.confidence.value))

    print_section("Rules")
    for rule in result.reasons:
        print(f"  {rule}")

    print_section("Metrics")
    for key, value in result.metrics.items():
        if value is not None:
            print(
                f"  {key}: {value:.4f}"
                if isinstance(value, float)
                else f"  {key}: {value}"
            )

    if result.red_flags:
        print_section("Red flags")
        for flag in result.red_flags:
            print(f"  {red('•')} {flag}")

    print_section("Sources")
    for source in result.sources:
        print(f"  {dim(source.book)} ({source.year}), {source.page}")
