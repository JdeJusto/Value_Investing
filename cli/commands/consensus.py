"""`consensus` — one ticker's aggregated verdicts from the consensus file.

Read-only: the CLI never recomputes methodologies; it reads the JSON written
by ``scripts.compute_consensus_rankings.py`` (see ``docs/consensus_screener.md``).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from backend.app.cli import add_demo_argument
from backend.services import cli_output
from backend.services.consensus_service import (
    CompanyConsensus,
    ConsensusReport,
    ConsensusService,
    default_consensus_dir,
)
from cli.formatters import fmt_dollar, print_header, print_table


def add_common_arguments(parser) -> None:
    """Flags shared by the three consensus commands."""
    parser.add_argument("--universe", default="sp500", help="sp500 | nasdaq100 | all")
    parser.add_argument(
        "--date", default=None, help="consensus date (YYYY-MM-DD; default: latest)"
    )
    parser.add_argument(
        "--csv", type=Path, default=None, help="export the output to CSV"
    )
    add_demo_argument(parser)


def missing_message(args) -> str:
    """Actionable message when no consensus file matches the filters."""
    date = f" and date {args.date}" if getattr(args, "date", None) else ""
    return (
        f"No consensus file found for universe {args.universe}{date}. "
        "Run: python -m scripts.compute_consensus_rankings "
        f"--universe {args.universe}"
    )


def load_report(args) -> ConsensusReport | None:
    """Newest report matching ``--universe``/``--date``, or None."""
    directory = default_consensus_dir()
    service = ConsensusService(directory=directory)
    chosen: Path | None = None
    chosen_date = ""
    for path in sorted(directory.glob("consensus_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            args.universe != "all"
            and str(payload.get("universe") or "") != args.universe
        ):
            continue
        report_date = str(payload.get("date") or "")
        if args.date is not None and report_date != args.date:
            continue
        if chosen is None or report_date > chosen_date:
            chosen, chosen_date = path, report_date
    if chosen is None:
        return None
    return service.load_file(chosen)


def compact_verdicts(company: CompanyConsensus) -> str:
    """Verdicts in the file's canonical methodology order, slash-separated."""
    return "/".join(company.verdicts.values())


def format_price(company: CompanyConsensus) -> str:
    return fmt_dollar(company.price) if company.price is not None else "N/A"


def write_csv(path: Path, rows: list[dict]) -> None:
    """Write the command rows to ``path`` (no-op for an empty table)."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  CSV written to {path}")


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "consensus",
        help="Show one ticker's consensus verdicts",
        description="Read the precomputed consensus file and print one company.",
    )
    parser.add_argument("ticker", type=str, help="Ticker (e.g. AAPL)")
    add_common_arguments(parser)
    parser.set_defaults(func=_run)


def _run(args) -> None:
    ticker = args.ticker.upper().strip()
    report = load_report(args)
    if report is None:
        print(missing_message(args))
        return
    company = next(
        (candidate for candidate in report.companies if candidate.ticker == ticker),
        None,
    )
    if company is None:
        print(
            f"Ticker {ticker} not found in the latest consensus "
            f"({report.universe}, {report.date}).\n"
            "Run: python -m scripts.compute_consensus_rankings "
            f"--universe {report.universe}"
        )
        return

    print_header(f"Consensus — {ticker} ({company.name})")
    print(f"  As of: {report.date} · Universe: {report.universe}")
    print()
    print_table(
        [("Methodology", 0), ("Verdict", 0)],
        [
            [methodology, cli_output.verdict_text(verdict)]
            for methodology, verdict in company.verdicts.items()
        ],
    )
    print()
    counts: dict[str, int] = {}
    for verdict in company.verdicts.values():
        counts[verdict] = counts.get(verdict, 0) + 1
    summary = "  ·  ".join(
        f"{key}: {counts.get(key, 0)}"
        for key in ("BUY", "WATCH", "HOLD", "AVOID", "N/A", "INSUFFICIENT_DATA")
    )
    print(f"  {summary}")
    print(f"  Consensus score: {company.consensus_score}  (BUYs minus AVOIDs)")
    print(f"  Lynch category: {company.lynch_category}")
    print(f"  Price at computation: {format_price(company)}")

    if args.csv:
        rows = [
            {
                "Ticker": company.ticker,
                "Name": company.name,
                "Category": company.lynch_category,
                "As of": report.date,
                "Universe": report.universe,
                "Methodology": methodology,
                "Verdict": verdict,
                "Price": format_price(company),
            }
            for methodology, verdict in company.verdicts.items()
        ]
        write_csv(args.csv, rows)
