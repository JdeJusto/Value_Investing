"""`analyze-marks` — run Howard Marks' measurable rules on one company."""

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
        "analyze-marks",
        help="Run Howard Marks' measurable rules on one company",
        description=(
            "Quantitative subset of *The Most Important Thing*: cycle "
            "position, resilience, margin of safety and quality persistence."
        ),
    )
    p.add_argument("ticker", help="Ticker to evaluate (e.g. AAPL)")
    add_refresh_arguments(p)
    add_demo_argument(p)
    p.set_defaults(func=_run)


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if abs(value) < 1:
        return f"{value:.2%}"
    return f"{value:,.2f}"


def _run(args):
    from backend.app.cli import build_financial_repository, refresh_analysis_inputs
    from backend.methodologies.registry import discover, registry
    from backend.services.price_service import get_price_service
    from cli.commands.preflight import require_known_tickers

    discover()
    require_known_tickers([args.ticker])
    refresh_analysis_inputs([args.ticker], args)
    if registry.get("marks") is None:
        print(red("ERROR: the 'marks' methodology is not registered."))
        return
    methodology = registry.get("marks")

    ticker = args.ticker.upper().strip()
    rows = [
        row
        for row in build_financial_repository().get_best_available(ticker)
        if row is not None
    ]
    result = methodology.evaluate(ticker, rows, get_price_service())

    print_header(f"Marks (quantitative subset) — {ticker}")
    print_key_value("Verdict", verdict_color(result.verdict.value))
    print_key_value("Score", f"{result.score:.2f}" if result.score is not None else "—")
    print_key_value("Confidence", confidence_color(result.confidence.value))

    if result.metrics:
        print_section("Metrics")
        for key, value in result.metrics.items():
            print_key_value(key, _fmt(value))

    if result.red_flags:
        print_section("Red flags")
        for flag in result.red_flags:
            print(f"  {red('•')} {flag}")

    print_section("Reasons")
    for reason in result.reasons:
        print(f"  • {reason}")

    print_section("Sources")
    for ref in result.sources:
        caution = f" — {ref.us_caution}" if ref.us_caution else ""
        print(f"  {dim('•')} {ref.book} ({ref.year}), {ref.page}{caution}")
