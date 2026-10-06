"""`consensus-ranking` — rank the consensus file by BUYs, AVOIDs or score."""

from __future__ import annotations

from cli.commands.consensus import (
    add_common_arguments,
    compact_verdicts,
    load_report,
    missing_message,
    write_csv,
)
from cli.formatters import print_header, print_table

_BY_KEYS = {
    "buys": lambda company: (
        -company.buy_count,
        -company.consensus_score,
        company.avoid_count,
        company.ticker,
    ),
    "avoid": lambda company: (
        -company.avoid_count,
        -company.buy_count,
        company.ticker,
    ),
    "score": lambda company: (
        -company.consensus_score,
        -company.buy_count,
        company.avoid_count,
        company.ticker,
    ),
}


def rank(companies, by: str = "buys"):
    """Ranked companies (all-INSUFFICIENT data holes excluded)."""
    return sorted(
        (company for company in companies if not company.is_data_hole),
        key=_BY_KEYS[by],
    )


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "consensus-ranking",
        help="Rank the consensus file by BUYs, AVOIDs or score",
        description="Read the precomputed consensus file and print the top rows.",
    )
    add_common_arguments(parser)
    parser.add_argument("--top", type=int, default=20, help="rows to show")
    parser.add_argument("--by", choices=sorted(_BY_KEYS), default="buys")
    parser.set_defaults(func=_run)


def _run(args) -> list[dict]:
    report = load_report(args)
    if report is None:
        print(missing_message(args))
        return []
    ranked = rank(report.companies, args.by)[: max(args.top, 0)]
    print_header(f"Consensus ranking — {report.universe} ({report.date}, by {args.by})")
    rows = [
        {
            "Rank": str(index),
            "Ticker": company.ticker,
            "Name": company.name,
            "Category": company.lynch_category,
            "BUYs": str(company.buy_count),
            "AVOIDs": str(company.avoid_count),
            "Score": f"{company.consensus_score:+d}",
            "Verdicts": compact_verdicts(company),
        }
        for index, company in enumerate(ranked, 1)
    ]
    print_table(
        [
            ("Rank", 1),
            ("Ticker", 0),
            ("Name", 0),
            ("Category", 0),
            ("BUYs", 1),
            ("AVOIDs", 1),
            ("Score", 1),
            ("Verdicts", 0),
        ],
        [
            [
                row["Rank"],
                row["Ticker"],
                row["Name"],
                row["Category"],
                row["BUYs"],
                row["AVOIDs"],
                row["Score"],
                row["Verdicts"],
            ]
            for row in rows
        ],
    )
    if args.csv:
        write_csv(args.csv, rows)
    return rows
