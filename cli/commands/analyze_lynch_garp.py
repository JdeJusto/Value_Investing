"""`analyze-lynch-garp` — run the Lynch GARP methodology on one company."""

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
        "analyze-lynch-garp",
        help="Run the Lynch GARP (growth at a reasonable price) screen on one company",
        description=(
            "Evaluates the five Lynch rules (PEG, earnings growth consistency, "
            "debt conservatism, inventory watch, dividend-adjusted PEG) and "
            "renders the verdict, score, confidence, red flags, metrics, "
            "reasons and sources."
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


def _confidence_color(confidence: str):
    return {"HIGH": green, "MEDIUM": yellow, "LOW": red}.get(confidence, lambda t: t)(
        confidence
    )


def _rule_color(outcome: str):
    return {
        "PASS": green,
        "WATCH": yellow,
        "FAIL": red,
        "INSUFFICIENT_DATA": dim,
    }.get(outcome, lambda t: t)(outcome)


def _run(args):
    from backend.app.cli import build_financial_repository
    from backend.methodologies.lynch_garp.methodology import LynchGARPMethodology
    from backend.methodologies.registry import discover, registry
    from backend.services.price_service import get_price_service

    discover()
    if registry.get("lynch_garp") is None:
        print(red("ERROR: the 'lynch_garp' methodology is not registered."))
        return
    methodology = LynchGARPMethodology()

    ticker = args.ticker.upper().strip()
    rows = [
        row
        for row in build_financial_repository().get_best_available(ticker)
        if row is not None
    ]
    service = get_price_service()
    price = service.get_current_price(ticker)
    try:
        market_cap = service.get_market_cap(ticker)
    except Exception:  # noqa: BLE001 — no market cap is not an error
        market_cap = None

    result = methodology.evaluate(ticker, rows, _Prices(price, market_cap))

    print_header(f"Lynch GARP analysis — {ticker}")
    print_key_value("Verdict", _verdict_color(result.verdict.value))
    score = "—" if result.score is None else f"{result.score:.2f}"
    print_key_value("Score", score)
    print_key_value("Confidence", _confidence_color(result.confidence.value))
    category = (result.metrics or {}).get("lynch_category_label")
    if category:
        print_key_value("Category", category)
    print()

    print_section("Rules")
    rule_outcomes = (result.metrics or {}).get("rule_outcomes", {})
    for rule in methodology.rules():
        outcome = rule_outcomes.get(rule.id, "N/A")
        print(f"  {_rule_color(outcome)}  {rule.id} — {rule.name}")
    print()

    if result.red_flags:
        print_section("Red flags")
        for flag in result.red_flags:
            print(f"  {red('•')} {flag}")
        print()

    print_section("Metrics")
    for key, value in result.metrics.items():
        if key in ("rule_outcomes", "lynch_category", "lynch_category_label"):
            continue
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

    def __init__(self, price, market_cap=None):
        self._price = price
        self._market_cap = market_cap

    def get_current_price(self, ticker):
        return self._price

    def get_market_cap(self, ticker):
        return self._market_cap
