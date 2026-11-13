"""`analyze-buffett-classic` — run the 20-rule Buffett/Munger screen."""

from __future__ import annotations

from backend.app.cli import add_demo_argument, add_refresh_arguments
from backend.methodologies.common.company_type import company_flags
from cli.formatters import (
    dim,
    header_with_flags,
    print_header,
    print_key_value,
    print_section,
    red,
    verdict_color,
)


def register(subparsers):
    p = subparsers.add_parser(
        "analyze-buffett-classic",
        help="[deprecated] Run the 20-rule Buffett/Munger quality compounder — use 'vi scorecard <ticker>'",
        description=(
            "Evaluates 20 explicit rules across moat, financial strength, "
            "earnings quality, capital allocation, valuation and management, "
            "aggregated with a weighted score (BUY >= 0.85, WATCH >= 0.70, "
            "HOLD >= 0.50). See docs/buffett_rules.md."
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
    methodology = registry.get("buffett_classic")
    if methodology is None:
        print("Error: buffett_classic methodology not registered")
        return

    repo = build_financial_repository()
    rows = repo.get_best_available(args.ticker)
    if not rows:
        print(f"No fundamentals found for {args.ticker}")
        return

    prices = get_price_service()
    result = methodology.evaluate(args.ticker, rows, prices)
    result.flags = company_flags(rows[0] if rows else None)

    print_header(
        header_with_flags(f"Buffett classic analysis — {args.ticker}", result.flags)
    )
    print_key_value("Verdict", verdict_color(result.verdict.value))
    print_key_value("Score", f"{result.score:.2f}" if result.score is not None else "—")
    print_key_value("Confidence", result.confidence.value)

    print_section("Metrics")
    for key, value in result.metrics.items():
        if value is None:
            continue
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        elif isinstance(value, dict):
            print(f"  {key}: {value}")
        else:
            print(f"  {key}: {value}")

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
