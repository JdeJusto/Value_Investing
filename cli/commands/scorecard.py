"""CLI: the six-dimension scorecard for one company.

Pure presentation: the command builds the shared :class:`ScorecardService`
and renders its :class:`Scorecard` — it never computes a financial figure.
Missing data is shown as ``INSUFFICIENT`` (with a ``—`` score), never as a 0.

Exit codes: ``0`` success, ``2`` unknown ticker, ``3`` any other error.
"""

from __future__ import annotations

import json

from rich.text import Text

from backend.services import cli_output
from cli.formatters import print_header, red

#: Per-rule glyph and color (PASS / WATCH / FAIL / INSUFFICIENT).
_STATUS_MARK = {
    "PASS": ("✓", cli_output.ACCENT),
    "WATCH": ("⚠", "yellow"),
    "FAIL": ("✗", cli_output.DANGER),
    "INSUFFICIENT": ("·", cli_output.MUTED),
}

#: Dimension verdict -> palette style.
_VERDICT_STYLE = {
    "Strong": cli_output.ACCENT,
    "Mixed": "yellow",
    "Weak": cli_output.DANGER,
    "Insufficient": cli_output.MUTED,
}


def register(subparsers):
    p = subparsers.add_parser(
        "scorecard",
        help="Six-dimension scorecard (Growth, Profitability, Valuation...)",
        description=(
            "Render the six-dimension scorecard for a ticker: each dimension's "
            "score, verdict and the rules behind it. Every value comes from the "
            "existing analysis services; missing data is shown as INSUFFICIENT, "
            "never fabricated. Use --json for the raw payload."
        ),
    )
    p.add_argument("ticker", help="Ticker (e.g. AAPL)")
    p.add_argument(
        "--period",
        default="FY",
        help="Fiscal period (default: FY; Q1-Q4 where stored)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print the raw Scorecard payload as JSON (skips rendering)",
    )
    p.set_defaults(func=_run)
    return p


def _run(args):
    from backend.app.cli import build_financial_repository
    from backend.services.price_service import get_price_service
    from backend.services.scorecard_service import ScorecardService

    ticker = args.ticker.upper().strip()
    try:
        service = ScorecardService(
            build_financial_repository(), price_service=get_price_service()
        )
        card = service.build(ticker, args.period)
    except Exception as exc:
        print(f"  {red('ERROR:')} Could not build the scorecard for {ticker}: {exc}")
        raise SystemExit(3) from exc

    if card is None:
        print(f"  {red('ERROR:')} Unknown ticker: {ticker}")
        raise SystemExit(2)

    if args.json:
        print(json.dumps(card.to_dict(), indent=2))
        return

    _render(card)


def _render(card):
    sector = card.sector or "Unknown sector"
    print_header(f"{card.ticker} · {card.company} · {sector} · overall {card.overall}")
    console = cli_output.get_console()

    rows = []
    for dim in card.dimensions:
        rows.append(
            [
                dim.label,
                "—" if dim.score is None else f"{dim.score}/10",
                Text(dim.verdict, style=_VERDICT_STYLE.get(dim.verdict, "")),
                dim.trend,
                dim.confidence,
            ]
        )
    console.print()
    console.print(
        cli_output.data_table(
            [
                ("Dimension", 0),
                ("Score", 1),
                ("Verdict", 0),
                ("Trend", 0),
                ("Confidence", 0),
            ],
            rows,
        )
    )

    for dim in card.dimensions:
        _render_dimension(cli_output.get_console(), dim)

    if card.disagreements:
        console.print()
        console.print(Text("  Disagreements", style=cli_output.HEADER))
        console.print(cli_output.rule())
        for line in card.disagreements:
            console.print(cli_output.bullet_line(line), soft_wrap=True)

    print()
    print(f"  Data: Financial-DataBase · {card.period} · Prices not persisted.")


def _render_dimension(console, dim) -> None:
    score = "—" if dim.score is None else f"{dim.score}/10"
    line = Text("  ")
    line.append(dim.label, style=cli_output.HEADER)
    line.append(f"  (score {score} · ")
    line.append(dim.verdict, style=_VERDICT_STYLE.get(dim.verdict, ""))
    line.append(
        f" · {dim.evaluable_rules} rules · {dim.trend} · {dim.confidence} confidence)"
    )
    console.print()
    console.print(line, soft_wrap=True)
    console.print(cli_output.rule())
    for rule in dim.rules:
        console.print(_rule_line(rule), soft_wrap=True)


def _rule_line(rule) -> Text:
    mark, style = _STATUS_MARK.get(rule.status, ("·", cli_output.MUTED))
    line = Text("  ")
    line.append(f"{mark} ", style=style)
    line.append(f"{rule.label:<30}")
    line.append(f"{rule.value:>10}")
    line.append(f"   {rule.threshold}", style=cli_output.MUTED)
    return line
