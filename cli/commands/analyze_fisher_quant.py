"""`analyze-fisher-quant` — quantitative subset of Fisher's 15 points."""

from __future__ import annotations

from backend.app.cli import add_demo_argument, add_refresh_arguments
from cli.formatters import (
    dim,
    green,
    print_header,
    print_key_value,
    print_section,
    red,
    yellow,
)

_DISCLAIMER = (
    "This is a quantitative subset of Fisher's 15 points, not Fisher. "
    "The 11 remaining points require scuttlebutt."
)


def register(subparsers):
    p = subparsers.add_parser(
        "analyze-fisher-quant",
        help="Run Fisher's 4 quantifiable points (R&D, margins, costs, dilution)",
        description=(
            "Evaluates the quantitative subset of Philip Fisher's 15 points "
            "(3: R&D intensity, 5: profit margin, 10: cost control, "
            "13: equity financing). The other 11 points need scuttlebutt "
            "and are out of scope."
        ),
    )
    p.add_argument("ticker", help="Ticker to evaluate (e.g. AAPL)")
    add_refresh_arguments(p)
    add_demo_argument(p)
    p.set_defaults(func=_run)


_STATUS_COLORS = {
    "PASS": green,
    "WATCH": yellow,
    "FAIL": red,
    "INSUFFICIENT_DATA": dim,
}


def _verdict_color(verdict: str):
    return {
        "BUY": green,
        "WATCH": yellow,
        "HOLD": lambda t: t,
        "AVOID": red,
        "INSUFFICIENT_DATA": dim,
    }.get(verdict, lambda t: t)(verdict)


def _run(args):
    from backend.app.cli import build_financial_repository, refresh_analysis_inputs
    from backend.methodologies.registry import discover, registry
    from backend.services.price_service import get_price_service
    from cli.commands.preflight import require_known_tickers

    discover()
    require_known_tickers([args.ticker])
    refresh_analysis_inputs([args.ticker], args)
    methodology = registry.get("fisher_quantitative_subset")
    if methodology is None:
        print("Error: fisher_quantitative_subset methodology not registered")
        return

    repo = build_financial_repository()
    rows = repo.get_best_available(args.ticker)
    if not rows:
        print(f"No fundamentals found for {args.ticker}")
        return

    prices = get_price_service()
    result = methodology.evaluate(args.ticker, rows, prices)

    print_header(f"Fisher quantitative subset — {args.ticker}")
    print_key_value("Ticker", args.ticker.upper())
    print_key_value("Methodology", result.methodology)
    print_key_value("Verdict", _verdict_color(result.verdict.value))
    print_key_value("Score", f"{result.score:.2f}" if result.score is not None else "—")
    print_key_value("Confidence", result.confidence.value)

    print_section("Rules (4 of Fisher's 15 points)")
    for reason in result.reasons:
        status, _, detail = reason.partition(" ")
        color = _STATUS_COLORS.get(status, lambda t: t)
        print(f"  {color(status):<18} {detail}")

    print_section("Metrics")
    for key, value in result.metrics.items():
        if value is None:
            continue
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    if result.red_flags:
        print_section("Red flags")
        for flag in result.red_flags:
            print(f"  {red('•')} {flag}")

    print_section("Sources")
    for source in result.sources:
        print(f"  {dim(source.book)} ({source.year}), {source.page}")

    print_section("Disclaimer")
    print(f"  {dim(_DISCLAIMER)}")
