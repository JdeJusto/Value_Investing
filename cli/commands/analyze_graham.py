"""`analyze-graham` — run the Graham methodology on one company."""

from __future__ import annotations

from cli.formatters import (
    bold,
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
        "analyze-graham",
        help="Run the Graham defensive-investor screen on one company",
        description=(
            "Evaluates the seven Graham criteria plus the combined P/E x P/BV "
            "test and renders the verdict, score, confidence, criteria, red "
            "flags, metrics, reasons and sources."
        ),
    )
    p.add_argument("ticker", help="Ticker to evaluate (e.g. AAPL)")
    p.add_argument(
        "--era-adjustment",
        action="store_true",
        help="Rescale the size threshold to 2024 dollars (labelled graham_modernized)",
    )
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


def _confidence_color(confidence: str):
    return {"HIGH": green, "MEDIUM": yellow, "LOW": red}.get(confidence, lambda t: t)(
        confidence
    )


def _run(args):
    from backend.app.cli import build_financial_repository
    from backend.methodologies.graham.methodology import GrahamMethodology
    from backend.methodologies.registry import discover, registry
    from backend.services.price_service import get_price_service

    discover()
    if registry.get("graham") is None:
        print(red("ERROR: the 'graham' methodology is not registered."))
        return
    # A configured instance, so --era-adjustment reaches the methodology.
    methodology = GrahamMethodology(
        era_adjustment=getattr(args, "era_adjustment", False)
    )

    ticker = args.ticker.upper().strip()
    rows = [
        row
        for row in build_financial_repository().get_best_available(ticker)
        if row is not None
    ]
    price = get_price_service().get_current_price(ticker)

    result = methodology.evaluate(ticker, rows, _Prices(price))

    print_header(f"Graham analysis — {ticker}")
    print_key_value("Verdict", _verdict_color(result.verdict.value))
    score = "—" if result.score is None else f"{result.score:.2f}"
    print_key_value("Score", score)
    print_key_value("Confidence", _confidence_color(result.confidence.value))
    print()

    print_section("Criteria")
    for rule_id in result.passed_rules:
        print(f"  {green('PASS')}  {rule_id}")
    for rule_id in result.failed_rules:
        print(f"  {red('FAIL')}  {rule_id}")
    unknown = [
        rule.id
        for rule in methodology.rules()
        if rule.id not in result.passed_rules and rule.id not in result.failed_rules
    ]
    for rule_id in unknown:
        print(f"  {dim('N/A')}  {rule_id}")
    print()

    if result.red_flags:
        print_section("Red flags")
        for flag in result.red_flags:
            print(f"  {red('•')} {flag}")
        print()

    print_section("Metrics")
    for key, value in result.metrics.items():
        if value is None:
            formatted = dim("—")
        elif isinstance(value, float):
            formatted = f"{value:,.2f}"
        else:
            formatted = str(value)
        print_key_value(key, formatted)
    print()

    print_section("Reasons")
    for reason in result.reasons:
        print(f"  • {reason}")
    print()

    print_section("Sources")
    for ref in result.sources:
        caution = f" — {ref.us_caution}" if ref.us_caution else ""
        print(f"  {dim('•')} {ref.book} ({ref.year}), {ref.page}{caution}")


class _Prices:
    """Adapter so the methodology can ask for a price without knowing PriceService."""

    def __init__(self, price):
        self._price = price

    def get_current_price(self, ticker):
        return self._price
