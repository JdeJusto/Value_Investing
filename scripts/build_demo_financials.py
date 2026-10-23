"""Build the demo Financials fixtures: ``data/demo/financials/<TICKER>.json``.

For every ticker of the offline demo bundle the full FY view (10 years) is
built from Financial-DataBase and written in the payload shape the
``FinancialsViewService`` reads in demo mode. The balance rows follow the
Fix-B concept map (``ui.balance_map``): every mapped face line, the reported
subtotals, the statement totals and the memoranda are kept, so the demo
T-view renders the same lines as the live one. The income and cash-flow
rows stay capped (iconic concepts first, then the best year coverage) to
keep the offline bundle small. No network, no SEC.

Run: ``python -m scripts.build_demo_financials`` (needs the FDB database).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.cli import build_financial_repository
from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)
from backend.services.alert_service import AlertService, alerts_to_payload
from backend.services.demo_mode import DEMO_TICKERS, is_demo
from backend.services.financial_insights_service import (
    FinancialInsightsService,
    report_to_payload,
)
from backend.services.financials_view_service import (
    CONCEPT_LABELS,
    FinancialsRow,
    FinancialsViewService,
    classify_concept,
)
from ui.balance_map import (
    BALANCE_MAP,
    MASS_ORDER,
    MASS_SUBTOTAL_CONCEPTS,
    MEMORANDUM_CONCEPTS,
    TOTAL_CONCEPTS,
)

MAX_YEARS = 10
#: Per-statement quotas for the rows that do not feed the T-view: they
#: guarantee every sub-tab has content while keeping each fixture under
#: the ~30 KB demo cap and the whole demo bundle below its size guard
#: (test_demo_mode) together with the insights fixtures. The balance rows
#: are NOT capped: the Fix-B map decides which face lines are kept.
QUOTAS = {
    "income_statement": 8,
    "cash_flow": 8,
    "other": 4,
}
TARGET = REPO_ROOT / "data" / "demo" / "financials"


def balance_concept_order() -> list[str]:
    """Balance-relevant concepts, in the order the T view renders them.

    The T view resolves its lines through ``BALANCE_MAP`` (mass -> alias
    slots), then the reported subtotals of each mass, then the statement
    totals, then the memoranda. The order is only used to decide *which*
    concepts are balance-relevant; the fixture keeps the live display order
    (label, then concept).
    """
    order: list[str] = []
    for mass in MASS_ORDER:
        for slot in BALANCE_MAP.get(mass, []):
            order.extend(slot)
    for mass in MASS_ORDER:
        order.extend(MASS_SUBTOTAL_CONCEPTS.get(mass, []))
    for concepts in TOTAL_CONCEPTS.values():
        order.extend(concepts)
    order.extend(sorted(MEMORANDUM_CONCEPTS))
    return order


#: Every concept that can render inside the T view (face lines, reported
#: subtotals, statement totals and the memoranda).
BALANCE_CONCEPTS: set[str] = set(balance_concept_order())


def _row_payload(row: FinancialsRow) -> dict:
    return {
        "concept": row.concept,
        "label": row.label,
        "values": {
            str(year): value for year, value in sorted(row.values.items(), reverse=True)
        },
        "unit": row.unit,
    }


def _top(rows: list[FinancialsRow], limit: int) -> list[FinancialsRow]:
    """Iconic (curated-label) concepts first, then most-covered, then alpha."""
    return sorted(
        rows,
        key=lambda row: (
            0 if row.concept in CONCEPT_LABELS else 1,
            -len(row.values),
            row.label.lower(),
            row.concept,
        ),
    )[:limit]


def _display_order(rows: list[FinancialsRow]) -> list[FinancialsRow]:
    """Sort the kept rows the way the live view sorts them (label, concept)."""
    return sorted(rows, key=lambda row: (row.label.lower(), row.concept))


def build_fixture(
    ticker: str, service: FinancialsViewService
) -> tuple[dict | None, dict | None, dict | None]:
    """(view payload, insights payload, alerts payload) from one facts read."""
    facts = service.fetch_facts(ticker, "FY", MAX_YEARS)
    view = service.build(ticker, "FY", MAX_YEARS, facts=facts, abbreviate=True)
    if view is None:
        return None, None, None
    report = FinancialInsightsService(facts, ticker, view.company_name).build(
        abbreviate=True
    )
    alerts = AlertService(facts).build(ticker, view.company_name, "FY", abbreviate=True)

    # Bucket every row with the same classifier the live view uses, so the
    # demo sub-tabs hold the same concepts as the live ones.
    buckets: dict[str, list[FinancialsRow]] = {
        "balance_sheet": [],
        "income_statement": [],
        "cash_flow": [],
        "other": [],
    }
    for row in (
        view.balance_sheet + view.income_statement + view.cash_flow + view.other
    ):
        buckets[classify_concept(row.concept)].append(row)

    # Balance rows: every Fix-B relevant concept (face lines, subtotals,
    # totals, memoranda), whichever bucket the classifier put it in. They
    # feed the T view, which reads both buckets.
    balance_rows = [
        row
        for row in buckets["balance_sheet"] + buckets["other"]
        if row.concept in BALANCE_CONCEPTS
    ]
    # The rest of the "other" bucket stays capped: it is noise for the T
    # view and the main cost driver of the bundle size.
    other_rows = _top(
        [row for row in buckets["other"] if row.concept not in BALANCE_CONCEPTS],
        QUOTAS["other"],
    )
    kept = {
        "balance_sheet": _display_order(balance_rows),
        "income_statement": _display_order(
            _top(buckets["income_statement"], QUOTAS["income_statement"])
        ),
        "cash_flow": _display_order(_top(buckets["cash_flow"], QUOTAS["cash_flow"])),
        "other": _display_order(other_rows),
    }
    total_rows = (
        len(view.balance_sheet)
        + len(view.income_statement)
        + len(view.cash_flow)
        + len(view.other)
    )
    kept_rows = sum(len(rows) for rows in kept.values())
    payload = {
        "ticker": view.ticker,
        "company_name": view.company_name,
        "fiscal_period": "FY",
        "years": view.years,
        "note": (
            f"Demo fixture: {kept_rows} of {total_rows} concepts, "
            f"{len(view.years)} most recent fiscal years. The balance rows "
            "follow the Fix-B concept map (every mapped face line, the "
            "reported subtotals, the statement totals and the memoranda), "
            "so the T-format balance view matches the live one; the income "
            "and cash-flow rows are the iconic concepts first."
        ),
        "balance_sheet": [_row_payload(row) for row in kept["balance_sheet"]],
        "income_statement": [_row_payload(row) for row in kept["income_statement"]],
        "cash_flow": [_row_payload(row) for row in kept["cash_flow"]],
        "other": [_row_payload(row) for row in kept["other"]],
        "unmatched_count": len(kept["other"]),
    }
    return payload, report_to_payload(report), alerts_to_payload(alerts)


def write_fixture(
    target: Path, ticker: str, payload: dict, insights: dict, alerts: dict
) -> int:
    """Write the three fixture files of one ticker; returns the rows kept."""
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{ticker}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (target / f"{ticker}_insights.json").write_text(
        json.dumps(insights, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (target / f"{ticker}_alerts.json").write_text(
        json.dumps(alerts, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return sum(
        len(payload[bucket])
        for bucket in (
            "balance_sheet",
            "income_statement",
            "cash_flow",
            "other",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tickers",
        nargs="*",
        help="tickers to build (default: every ticker of the demo bundle)",
    )
    args = parser.parse_args()

    if is_demo():
        print(
            "Refusing to run in demo mode (VI_DEMO=1): the fixtures are built "
            "from Financial-DataBase, not from the offline bundle.",
        )
        return 1

    tickers = tuple(t.upper() for t in args.tickers) or tuple(sorted(DEMO_TICKERS))
    repository = build_financial_repository()
    if not isinstance(repository, FinancialDatabaseRepository):
        print(
            "Financial-DataBase is not reachable: the demo fixtures are built "
            "from it (the JSON fallback holds no XBRL concepts).",
        )
        return 1
    service = FinancialsViewService(repository)
    TARGET.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    for ticker in tickers:
        payload, insights, alerts = build_fixture(ticker, service)
        if payload is None or insights is None or alerts is None:
            print(f"{ticker}: no facts stored, skipped")
            continue
        rows = write_fixture(TARGET, ticker, payload, insights, alerts)
        size = (TARGET / f"{ticker}.json").stat().st_size
        total_bytes += size
        print(
            f"{ticker}: {rows} rows ({len(payload['balance_sheet'])} balance), "
            f"{size / 1024:.1f} KB view"
        )
    print(
        f"{len(tickers)} tickers, {total_bytes / 1024:.0f} KB of view payloads "
        f"in {TARGET}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
