"""CLI: watchlist monitoring with statuses and CSV export."""

import csv
import os

from backend.app.cli import build_watchlist_service
from backend.watchlist import BOUGHT, DISCARDED, MONITORING
from cli.formatters import (
    bold,
    dim,
    green,
    print_header,
    print_table,
    yellow,
)


def register(subparsers):
    p = subparsers.add_parser(
        "watchlist",
        help="Track companies under monitoring",
        description=(
            "Manages a persistent watchlist (add/remove/status/list) "
            "enriched with scores, signal and opportunity, and exports "
            "results to CSV."
        ),
    )
    sub = p.add_subparsers(dest="action", title="Actions", required=True)

    add = sub.add_parser("add", help="Add a ticker to the watchlist")
    add.add_argument("ticker", type=str)
    add.add_argument("--note", type=str, default="", help="Reason for monitoring")
    add.set_defaults(func=_add)

    remove = sub.add_parser("remove", help="Remove a ticker")
    remove.add_argument("ticker", type=str)
    remove.set_defaults(func=_remove)

    status = sub.add_parser(
        "status", help="Change the status (MONITORING/BOUGHT/DISCARDED)"
    )
    status.add_argument("ticker", type=str)
    status.add_argument(
        "--status", type=str, required=True, choices=(MONITORING, BOUGHT, DISCARDED)
    )
    status.set_defaults(func=_status)

    sub.add_parser("list", help="Show the enriched watchlist").set_defaults(func=_list)

    export = sub.add_parser("export", help="Export the watchlist to CSV")
    export.add_argument("path", type=str, nargs="?", default=None)
    export.add_argument(
        "--monitoring-only",
        action="store_true",
        help="Only items in MONITORING status",
    )
    export.set_defaults(func=_export)

    p.set_defaults(
        func=lambda args: p.print_help() if not hasattr(args, "action") else None
    )


def _add(args):
    service = build_watchlist_service()
    item = service.add(args.ticker, note=args.note)
    print(green(f"{item.ticker} added to the watchlist ({item.status})."))


def _remove(args):
    service = build_watchlist_service()
    removed = service.remove(args.ticker)
    if removed is None:
        print(yellow(f"{args.ticker.upper()} is not in the watchlist."))
        return
    print(green(f"{removed.ticker} removed from the watchlist."))


def _status(args):
    service = build_watchlist_service()
    item = service.set_status(args.ticker, args.status)
    if item is None:
        print(yellow(f"{args.ticker.upper()} is not in the watchlist."))
        return
    print(green(f"{item.ticker} -> {item.status}."))


def _status_color(status):
    return {
        MONITORING: yellow(status),
        BOUGHT: green(status),
        DISCARDED: dim(status),
    }.get(status, status)


def _list(args):
    service = build_watchlist_service()
    rows = service.list_view()

    print_header(f"Watchlist ({len(rows)} items)")
    if not rows:
        print(f"  {yellow('Empty.')} Add tickers with 'main.py watchlist add TICKER'.")
        return

    headers = [
        ("Ticker", 0),
        ("Status", 0),
        ("Buffett", 1),
        ("Moat", 0),
        ("Ranking", 1),
        ("Signal", 0),
        ("Trigger", 0),
        ("Opportunity", 0),
    ]
    table = []
    for row in rows:
        table.append(
            [
                row["ticker"],
                _status_color(row["status"]),
                (
                    f"{row['buffett_score']:.0f}"
                    if row["buffett_score"] is not None
                    else dim("-")
                ),
                row["moat"] if row["moat"] else dim("-"),
                f"{row['rank']:.1f}" if row["rank"] is not None else dim("-"),
                row["signal"] if row["signal"] else dim("-"),
                row["trigger"] if row["trigger"] else dim("-"),
                row["opportunity_type"] if row["opportunity_type"] else dim("-"),
            ]
        )
    print_table(headers, table)

    noted = [r for r in rows if r["note"]]
    if noted:
        print(f"\n  {bold('Notes')}")
        for row in noted:
            print(f"  - {bold(row['ticker'])}: {row['note']}")
    print()
    print(green("Done."))


def _export(args):
    service = build_watchlist_service()
    rows = service.export_rows(only_monitoring=args.monitoring_only)
    path = args.path or "data/watchlist.csv"

    if not rows:
        print(yellow("Nothing to export."))
        return

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fields = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(green(f"{len(rows)} rows exported to {path}"))
