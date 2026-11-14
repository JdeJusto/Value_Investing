"""`consensus-ranking` — rank the consensus file by BUYs, AVOIDs or score."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from cli.commands.consensus import (
    add_common_arguments,
    available_consensus_universes,
    compact_verdicts,
    default_consensus_dir,
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
    """Ranked companies (data holes and all-N/A companies excluded)."""
    return sorted(
        (company for company in companies if not company.is_excluded),
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
    parser.add_argument(
        "--no-compute",
        action="store_true",
        help="Fail if the precomputed file is missing (do not auto-compute)",
    )
    parser.set_defaults(func=_run)


def _run(args) -> list[dict]:
    report = load_report(args)
    if report is None and not getattr(args, "no_compute", False):
        available = ", ".join(available_consensus_universes()) or "(none)"
        print(f"No precomputed consensus for '{args.universe}'.")
        print(f"Available: {available}")
        print()
        from backend.services.demo_mode import is_demo

        if is_demo():
            print(
                f"Demo mode has no precomputed file for '{args.universe}'. "
                "Run the command without --demo to compute it."
            )
            return []
        print(
            f"Computing consensus for '{args.universe}' (~2-5 min)... Ctrl+C to abort."
        )
        try:
            from scripts.compute_consensus_rankings import main as compute_main

            # The script names its output consensus_<date>.json, which would
            # overwrite another universe computed the same day. Give it a
            # scratch directory and move the result to a per-universe file.
            with tempfile.TemporaryDirectory() as scratch:
                argv = ["--universe", args.universe, "--output-dir", scratch]
                if getattr(args, "date", None):
                    argv += ["--date", args.date]
                compute_main(argv)
                generated = sorted(
                    Path(scratch).glob("consensus_*.json"),
                    key=lambda path: path.stat().st_mtime,
                )
                if not generated:
                    print(
                        "Computation finished but produced no consensus file.",
                        file=sys.stderr,
                    )
                    return []
                payload = json.loads(generated[-1].read_text(encoding="utf-8"))
                output_date = str(payload.get("date") or "").strip()
                target = (
                    default_consensus_dir()
                    / f"consensus_{output_date}_{args.universe}.json"
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(generated[-1]), target)
                print(f"Cached: {target}")
        except KeyboardInterrupt:
            print("\nAborted.")
            return []
        except Exception as exc:  # noqa: BLE001 — report and fail cleanly
            print(f"Failed to compute consensus: {exc}", file=sys.stderr)
            return []
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
