"""`analyze-greenblatt` — run the Greenblatt Magic Formula on one company."""

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


def register(subparsers):
    p = subparsers.add_parser(
        "analyze-greenblatt",
        help="Run the Greenblatt Magic Formula (weekly rankings) on one company",
        description=(
            "Looks the ticker up in the newest data/rankings/greenblatt_*.json "
            "and maps its combined-rank percentile to a verdict. Refresh the "
            "rankings with scripts/compute_greenblatt_rankings.py."
        ),
    )
    p.add_argument("ticker", help="Ticker to evaluate (e.g. AAPL)")
    add_refresh_arguments(p)
    add_demo_argument(p)
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
    if registry.get("greenblatt") is None:
        print(red("ERROR: the 'greenblatt' methodology is not registered."))
        return
    methodology = registry.get("greenblatt")

    ticker = args.ticker.upper().strip()
    rows = [
        row
        for row in build_financial_repository().get_best_available(ticker)
        if row is not None
    ]
    result = methodology.evaluate(ticker, rows, get_price_service())

    print_header(f"Greenblatt Magic Formula — {ticker}")
    print_key_value("Verdict", _verdict_color(result.verdict.value))
    print_key_value("Score", f"{result.score:.2f}" if result.score is not None else "—")
    print_key_value("Confidence", _confidence_color(result.confidence.value))

    if result.metrics:
        print_section("Metrics")
        for key, value in result.metrics.items():
            print_key_value(key, _fmt(value))

    print_section("Reasons")
    for reason in result.reasons:
        print(f"  • {reason}")

    print_section("Sources")
    for ref in result.sources:
        caution = f" — {ref.us_caution}" if ref.us_caution else ""
        print(f"  {dim('•')} {ref.book} ({ref.year}), {ref.page}{caution}")
