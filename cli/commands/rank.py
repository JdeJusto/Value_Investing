"""`rank` — rank tickers by one methodology or a combination.

Thin CLI wrapper over ``methodology_ranking_service``: all scoring and
ordering stay in the service.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.services import demo_mode
from backend.services.methodology_ranking_service import (
    CombinedRankedTicker,
    RankedTicker,
    rank_by_methodology,
    rank_combined,
)
from backend.services.ui_adapter import parse_universe_tickers
from cli import theme
from cli.formatters import print_table, red

_METHODOLOGY_ALIASES = {"lynch": "lynch_garp"}


def _methodology(name: str) -> str:
    value = name.strip()
    return _METHODOLOGY_ALIASES.get(value.lower(), value)


_UNIVERSE_LABELS = {
    "sp500": ["SP500"],
    "nasdaq100": ["NASDAQ100"],
    "russell2000": ["RUSSELL2000"],
    "all": ["ALL"],
}


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "rank",
        help="Rank tickers by methodology or a combination",
        description=(
            "Rank a universe with one methodology (--by) or with an "
            "AND/OR/weighted combination (--combine). Defaults to the demo "
            "universe for a quick smoke test."
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--by", metavar="METHOD", help="Single methodology")
    group.add_argument(
        "--combine",
        metavar="A,B",
        help="Comma-separated methodologies to combine",
    )
    parser.add_argument(
        "--strategy",
        choices=["and", "or", "weighted"],
        default="and",
        help="Combination strategy (default: and)",
    )
    parser.add_argument(
        "--universe",
        default="demo",
        help="demo | sp500 | nasdaq100 | russell2000 | all | path.csv",
    )
    parser.add_argument("--top", type=int, default=20, help="rows to show")
    parser.add_argument(
        "--include-na",
        action="store_true",
        help="Include N/A verdicts (with their reason)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the ranked payload as JSON",
    )
    parser.set_defaults(func=_run)


def _resolve_universe(name: str) -> list[str]:
    value = (name or "demo").strip()
    lowered = value.lower()
    if lowered == "demo":
        return list(demo_mode.DEMO_TICKERS)
    path = (
        Path(value) if value.lower().endswith(".csv") else Path("config/universe.csv")
    )
    if not path.exists():
        raise ValueError(f"Universe file not found: {path}")
    labels = _UNIVERSE_LABELS.get(lowered, ["ALL"])
    return parse_universe_tickers(path.read_text(encoding="utf-8"), labels)


def _single_dict(item: RankedTicker) -> dict:
    return {
        "ticker": item.ticker,
        "verdict": item.verdict.value,
        "score": item.score,
        "family": item.family,
        "n_a_reason": item.n_a_reason,
    }


def _combined_dict(item: CombinedRankedTicker) -> dict:
    return {
        "ticker": item.ticker,
        "verdict": item.combined_verdict.value,
        "score": item.combined_score,
        "rationale": item.rationale,
        "per_methodology": {
            name: _single_dict(result) for name, result in item.per_methodology.items()
        },
    }


def _run(args) -> None:
    try:
        universe = _resolve_universe(args.universe)
    except ValueError as exc:
        print(f"  {red('ERROR:')} {exc}")
        raise SystemExit(2) from exc

    if not universe:
        print(f"  {red('ERROR:')} The universe is empty.")
        raise SystemExit(2)

    top = max(1, int(args.top))
    try:
        if args.by:
            methodology = _methodology(args.by)
            results = rank_by_methodology(
                methodology,
                universe,
                top_n=top,
                include_na=args.include_na,
            )
            mode = f"by {methodology}"
        else:
            methodologies = [
                _methodology(item)
                for item in (args.combine or "").split(",")
                if item.strip()
            ]
            if not methodologies:
                raise ValueError("--combine needs at least one methodology")
            results = rank_combined(
                methodologies,
                universe,
                strategy=args.strategy,
                top_n=top,
            )
            mode = f"combine {','.join(methodologies)} ({args.strategy})"
    except ValueError as exc:
        print(f"  {red('ERROR:')} {exc}")
        raise SystemExit(2) from exc
    except Exception as exc:
        print(f"  {red('ERROR:')} Ranking failed: {exc}")
        raise SystemExit(3) from exc

    if args.json:
        payload = (
            [_single_dict(item) for item in results]
            if args.by
            else [_combined_dict(item) for item in results]
        )
        print(json.dumps(payload, indent=2, default=str))
        return

    theme.print_header(
        f"Ranking · {mode}",
        f"{args.universe} · {len(universe)} tickers · top {top}",
    )
    if args.by:
        _render_single(results, args.include_na)
    else:
        _render_combined(results)
    if args.include_na:
        if args.by:
            na_count = sum(1 for item in results if item.n_a_reason)
        else:
            na_count = sum(
                1
                for item in results
                if item.combined_verdict.value in {"N/A", "INSUFFICIENT_DATA"}
            )
        if na_count:
            print(theme.dim(f"  {na_count} rows with N/A / insufficient data"))


def _render_single(results: list[RankedTicker], include_na: bool) -> None:
    headers = [("Rank", 1), ("Ticker", 0), ("Verdict", 0), ("Score", 1), ("Family", 0)]
    if include_na:
        headers.append(("N/A reason", 0))
    rows = []
    for index, item in enumerate(results, 1):
        row = [
            str(index),
            item.ticker,
            theme.color_verdict(item.verdict),
            f"{item.score:.2f}" if item.score is not None else "—",
            item.family,
        ]
        if include_na:
            row.append(item.n_a_reason or "")
        rows.append(row)
    print_table(headers, rows)


def _render_combined(results: list[CombinedRankedTicker]) -> None:
    print_table(
        [("Rank", 1), ("Ticker", 0), ("Verdict", 0), ("Score", 1), ("Rationale", 0)],
        [
            [
                str(index),
                item.ticker,
                theme.color_verdict(item.combined_verdict),
                f"{item.combined_score:.2f}"
                if item.combined_score is not None
                else "—",
                item.rationale,
            ]
            for index, item in enumerate(results, 1)
        ],
    )
