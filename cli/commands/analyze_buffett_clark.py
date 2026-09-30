"""`analyze-buffett-clark` — run the Buffett/Clark methodology on one company."""

from __future__ import annotations

from backend.app.cli import add_refresh_arguments
from cli.formatters import (
    dim,
    green,
    print_header,
    print_key_value,
    print_section,
    red,
    yellow,
)


def register(subparsers):
    p = subparsers.add_parser(
        "analyze-buffett-clark",
        help="Run the Buffett/Clark DCA screen on one company",
        description=(
            "Evaluates the seven Buffett/Clark rules for durable competitive "
            "advantage and renders the verdict, score, confidence, metrics, "
            "reasons and sources."
        ),
    )
    p.add_argument("ticker", help="Ticker to evaluate (e.g. AAPL)")
    add_refresh_arguments(p)
    p.set_defaults(func=_run)


def _verdict_color(verdict: str):
    return {
        "BUY": green,
        "WATCH": yellow,
        "HOLD": lambda t: t,
        "AVOID": red,
        "INSUFFICIENT_DATA": dim,
    }.get(verdict, lambda t: t)(verdict)


def _confidence_color(confidence: str):
    return {"HIGH": green, "MEDIUM": yellow, "LOW": red}.get(confidence, lambda t: t)(
        confidence
    )


def _run(args):
    from backend.app.cli import build_financial_repository, refresh_analysis_inputs
    from backend.methodologies.registry import discover, registry
    from backend.services.price_service import get_price_service
    from cli.commands.preflight import require_known_tickers

    discover()
    require_known_tickers([args.ticker])
    refresh_analysis_inputs([args.ticker], args)
    methodology = registry.get("buffett_clark")
    if methodology is None:
        print("Error: buffett_clark methodology not registered")
        return

    repo = build_financial_repository()
    rows = repo.get_best_available(args.ticker)
    if not rows:
        print(f"No fundamentals found for {args.ticker}")
        return

    prices = get_price_service()
    result = methodology.evaluate(args.ticker, rows, prices)

    print_header(f"Buffett/Clark analysis — {args.ticker}")
    print_key_value("Verdict", _verdict_color(result.verdict.value))
    print_key_value("Score", f"{result.score:.2f}" if result.score is not None else "—")
    print_key_value("Confidence", _confidence_color(result.confidence.value))

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

    if result.reasons:
        print_section("Reasons")
        for reason in result.reasons:
            print(f"  {reason}")

    if result.red_flags:
        print_section("Red flags")
        for flag in result.red_flags:
            print(f"  {red('•')} {flag}")

    print_section("Sources")
    for source in result.sources:
        print(f"  {dim(source.book)} ({source.year}), {source.page}")
