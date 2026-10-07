"""`consensus-by-category` — top companies per Lynch category by score."""

from __future__ import annotations

from backend.services import cli_output
from backend.services.consensus_service import LYNCH_CATEGORIES
from cli.commands.consensus import (
    add_common_arguments,
    load_report,
    missing_message,
    write_csv,
)
from cli.formatters import print_header, print_table

_EMPTY_NOTE = "No companies in this category in the current universe."


def rank_category(members, per_category: int):
    """Top ``per_category`` companies in one category, by consensus score."""
    ordered = sorted(
        (company for company in members if not company.is_data_hole),
        key=lambda company: (
            -company.consensus_score,
            -company.buy_count,
            company.avoid_count,
            company.ticker,
        ),
    )
    return ordered[: max(per_category, 0)]


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "consensus-by-category",
        help="Top companies per Lynch category by consensus score",
        description="Read the precomputed consensus file and group it by category.",
    )
    add_common_arguments(parser)
    parser.add_argument("--per-category", type=int, default=5, help="rows per category")
    parser.set_defaults(func=_run)


def _run(args) -> list[dict]:
    report = load_report(args)
    if report is None:
        print(missing_message(args))
        return []
    print_header(f"Consensus by Lynch category — {report.universe} ({report.date})")
    csv_rows: list[dict] = []
    console = cli_output.get_console()
    for category in LYNCH_CATEGORIES:
        members = [
            company
            for company in report.companies
            if company.lynch_category == category
        ]
        print()
        console.print(cli_output.heading(category), soft_wrap=True)
        console.print(cli_output.rule(length=48), soft_wrap=True)
        ranked = rank_category(members, args.per_category)
        if not ranked:
            print(f"  {_EMPTY_NOTE}")
            continue
        print_table(
            [
                ("#", 1),
                ("Ticker", 0),
                ("Name", 0),
                ("BUYs", 1),
                ("AVOIDs", 1),
                ("Score", 1),
            ],
            [
                [
                    str(index),
                    company.ticker,
                    company.name,
                    str(company.buy_count),
                    str(company.avoid_count),
                    f"{company.consensus_score:+d}",
                ]
                for index, company in enumerate(ranked, 1)
            ],
        )
        for index, company in enumerate(ranked, 1):
            csv_rows.append(
                {
                    "Category": category,
                    "Rank": str(index),
                    "Ticker": company.ticker,
                    "Name": company.name,
                    "BUYs": str(company.buy_count),
                    "AVOIDs": str(company.avoid_count),
                    "Score": f"{company.consensus_score:+d}",
                }
            )
    if args.csv:
        write_csv(args.csv, csv_rows)
    return csv_rows
