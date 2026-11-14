"""`consensus` — one ticker's aggregated verdicts from the consensus file.

Read-only: the CLI never recomputes methodologies; it reads the JSON written
by ``scripts.compute_consensus_rankings.py`` (see ``docs/consensus_screener.md``).
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.cli import add_demo_argument
from backend.services import cli_output
from backend.services.consensus_service import (
    CompanyConsensus,
    ConsensusReport,
    ConsensusService,
    default_consensus_dir,
    summarize_verdicts,
)
from cli.formatters import fmt_dollar, print_header, print_table, red


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


def available_consensus_universes(directory: Path | None = None) -> list[str]:
    """Universes with a precomputed consensus file (payload, not filename)."""
    directory = directory or default_consensus_dir()
    found: set[str] = set()
    if not directory.exists():
        return []
    for path in sorted(directory.glob("consensus_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        universe = str(payload.get("universe") or "").strip()
        if universe:
            found.add(universe)
    return sorted(found)


def missing_message(args) -> str:
    """Actionable message when no consensus file matches the filters."""
    date = f" and date {args.date}" if getattr(args, "date", None) else ""
    available = ", ".join(available_consensus_universes()) or "(none)"
    return (
        f"No precomputed consensus for universe {args.universe}{date}.\n"
        f"Available: {available}\n"
        f"Run: vi consensus-ranking --universe {args.universe}"
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
    """Show one ticker's consensus by running the methodologies directly.

    A precomputed file is only needed to rank a whole universe; a single
    ticker can be evaluated on demand. ``--universe`` is accepted for
    compatibility but deliberately ignored here.
    """
    from backend.app.cli import build_financial_repository
    from backend.services.price_service import get_price_service
    from backend.services.ui_adapter import run_methodologies

    ticker = args.ticker.upper().strip()
    try:
        repository = build_financial_repository()
        rows = [row for row in repository.get_best_available(ticker) if row is not None]
    except Exception as exc:  # noqa: BLE001 — DB boundary
        print(red(f"ERROR: could not load {ticker}: {exc}"))
        return
    if not rows:
        print(red(f"Unknown ticker or no fundamentals: {ticker}"))
        return

    price_service = get_price_service()
    try:
        price = price_service.get_current_price(ticker)
        market_cap = price_service.get_market_cap(ticker) if price else None
        beta = price_service.get_beta(ticker)
    except Exception:  # noqa: BLE001 — prices are optional for the verdicts
        price, market_cap, beta = None, None, None

    view = run_methodologies(ticker, rows, price, market_cap, beta=beta)
    verdicts = {
        str(detail["methodology"]): str(detail["verdict"]) for detail in view.details
    }
    summary = summarize_verdicts(verdicts)
    name = ticker
    getter = getattr(repository, "get_company_name", None)
    if callable(getter):
        try:
            name = getter(ticker) or ticker
        except Exception:  # noqa: BLE001 — the name is cosmetic
            name = ticker

    company = CompanyConsensus(
        ticker=ticker,
        name=name,
        lynch_category=view.category or "Unknown",
        verdicts=verdicts,
        price=price,
        prices_available=price is not None,
        flags=tuple(view.details[0].get("flags", ())) if view.details else (),
        buy_count=summary["buy_count"],
        avoid_count=summary["avoid_count"],
        insufficient_count=summary["insufficient_count"],
        consensus_score=summary["consensus_score"],
        na_count=summary["na_count"],
    )
    today = datetime.now(tz=UTC).date().isoformat()
    _render_company(company, today, "single ticker", args.csv)


def _render_company(
    company: CompanyConsensus,
    report_date: str,
    universe: str,
    csv_path: Path | None,
) -> None:
    print_header(f"Consensus — {company.ticker} ({company.name})")
    print(f"  As of: {report_date} · Universe: {universe}")
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
        for key in (
            "STRONG_BUY",
            "BUY",
            "WEAK_BUY",
            "WATCH",
            "HOLD",
            "AVOID",
            "N/A",
            "INSUFFICIENT_DATA",
        )
    )
    print(f"  {summary}")
    print(f"  Consensus score: {company.consensus_score}  (BUYs minus AVOIDs)")
    print(f"  Lynch category: {company.lynch_category}")
    print(f"  Price at computation: {format_price(company)}")

    if csv_path:
        rows = [
            {
                "Ticker": company.ticker,
                "Name": company.name,
                "Category": company.lynch_category,
                "As of": report_date,
                "Universe": universe,
                "Methodology": methodology,
                "Verdict": verdict,
                "Price": format_price(company),
            }
            for methodology, verdict in company.verdicts.items()
        ]
        write_csv(csv_path, rows)
