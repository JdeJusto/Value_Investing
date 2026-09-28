"""`compare-methodologies` — side-by-side comparison with a disagreement summary."""

from __future__ import annotations

from cli.formatters import bold, dim, print_header, print_section


def register(subparsers):
    p = subparsers.add_parser(
        "compare-methodologies",
        help="Compare methodologies side by side for one company",
        description=(
            "Runs every registered methodology on one ticker and renders a "
            "side-by-side table plus a Disagreement summary. The summary "
            "groups verdicts by family so 3- and 4-way disagreements stay "
            "readable."
        ),
    )
    p.add_argument("ticker", help="Ticker to compare (e.g. AAPL)")
    p.add_argument(
        "--methodologies",
        default="",
        help="Comma-separated subset (default: all registered)",
    )
    p.set_defaults(func=_run)


def _verdict_color(verdict: str):
    from cli.formatters import green, red, yellow

    return {
        "BUY": green,
        "WATCH": yellow,
        "AVOID": red,
        "INSUFFICIENT_DATA": dim,
    }.get(verdict, lambda t: t)(verdict)


def _run(args):
    from backend.app.cli import build_financial_repository
    from backend.methodologies.registry import discover, registry
    from backend.services.price_service import get_price_service

    discover()

    names = [
        n.strip() for n in args.methodologies.split(",") if n.strip()
    ] or registry.list()

    ticker = args.ticker.upper().strip()
    rows = [
        row
        for row in build_financial_repository().get_best_available(ticker)
        if row is not None
    ]
    price = get_price_service().get_current_price(ticker)

    results = []
    for name in names:
        methodology = registry.get(name)
        if methodology is None:
            from cli.formatters import yellow

            print(yellow(f"WARNING: unknown methodology '{name}', skipped."))
            continue
        results.append(methodology.evaluate(ticker, rows, _Prices(price)))

    print_header(f"Methodology comparison — {ticker}")
    print(f"  {'methodology':<18} {'verdict':<18} {'score':<8} {'confidence':<10}")
    print(f"  {'-' * 18} {'-' * 18} {'-' * 8} {'-' * 10}")
    for result in results:
        score = "—" if result.score is None else f"{result.score:.1f}"
        print(
            f"  {result.methodology:<18} "
            f"{_verdict_color(result.verdict.value):<18} "
            f"{score:<8} "
            f"{result.confidence.value:<10}"
        )
    print()

    print_section("Disagreement summary")
    if len(results) < 2:
        print(
            dim(
                "  Only one methodology is registered; add more with "
                "'analyze-multi <ticker> --methodologies a,b,c'."
            )
        )
    else:
        unique = {result.verdict.value for result in results}
        if len(unique) == 1:
            print(dim("  All registered methodologies agree on this company."))
            return

        # Group by family so a 3- or 4-way disagreement stays readable.
        families: dict[str, list] = {}
        for result in results:
            families.setdefault(result.family, []).append(result)
        for family, members in sorted(families.items()):
            print(
                f"  {bold(family)} → "
                + ", ".join(
                    f"{member.methodology}={member.verdict.value}" for member in members
                )
            )
        print()

        value_members = [
            result
            for result in results
            if "VALUE" in result.family.upper() or "DEEP" in result.family.upper()
        ]
        quality_members = [
            result
            for result in results
            if "QUALITY" in result.family.upper()
            or "COMPOUNDER" in result.family.upper()
            or "DCA" in result.family.upper()
        ]
        if value_members and quality_members:
            value_names = ", ".join(m.methodology for m in value_members)
            quality_names = ", ".join(m.methodology for m in quality_members)
            print(
                dim(
                    f"  Why the families disagree: the value screen(s) "
                    f"({value_names}) judge price against assets/earnings "
                    f"and require a safety margin, so an expensive or "
                    f"levered balance sheet vetoes them. The quality "
                    f"screen(s) ({quality_names}) reward durable "
                    f"profitability and business strength without "
                    f"requiring a cheap price — exactly where a "
                    f"strong-but-expensive company splits them."
                )
            )
        else:
            print(dim("  The methodologies use different lenses; see reasons below."))
        print()

        for result in results:
            reasons = "; ".join(result.reasons[:2])
            print(f"  {bold(result.methodology)} ({result.verdict.value}): {reasons}")


class _Prices:
    """Adapter so a methodology can ask for a price without knowing PriceService."""

    def __init__(self, price):
        self._price = price

    def get_current_price(self, ticker):
        return self._price
