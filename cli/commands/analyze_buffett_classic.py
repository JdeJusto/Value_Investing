"""`analyze-buffett-classic` — run the wrapped Buffett 4-pillar filter on one company."""

from __future__ import annotations

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
        "analyze-buffett-classic",
        help="Run the Buffett/Munger 4-pillar qualitative filter (wrapped engine)",
        description=(
            "Evaluates the existing deterministic Buffett filter "
            "(profitability, financial strength, cash generation, stability) "
            "as a methodology. The engine in backend/intelligence is not "
            "modified; this command only maps its output to the framework."
        ),
    )
    p.add_argument("ticker", help="Ticker to evaluate (e.g. AAPL)")
    p.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip the on-demand SEC refresh before evaluating",
    )
    p.set_defaults(func=_run)


def _verdict_color(verdict: str):
    return {
        "BUY": green,
        "WATCH": yellow,
        "HOLD": lambda t: t,
        "AVOID": red,
        "INSUFFICIENT_DATA": dim,
    }.get(verdict, lambda t: t)(verdict)


def _run(args):
    from backend.app.cli import build_financial_repository
    from backend.methodologies.registry import discover, registry
    from backend.services.price_service import get_price_service

    discover()
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

    print_header(f"Buffett classic analysis — {args.ticker}")
    print_key_value("Verdict", _verdict_color(result.verdict.value))
    print_key_value("Score", f"{result.score:.2f}" if result.score is not None else "—")
    print_key_value("Confidence", result.confidence.value)

    print_section("Pillars")
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
