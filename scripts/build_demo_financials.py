"""Build the demo Financials fixtures: ``data/demo/financials/<TICKER>.json``.

For each demo ticker the full FY view (10 years) is built from
Financial-DataBase, capped to the top concepts per statement (by year
coverage) so each fixture stays ~30 KB, and written in the payload shape the
``FinancialsViewService`` reads in demo mode. No network, no SEC.

Run: ``python -m scripts.build_demo_financials`` (needs the FDB database).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.cli import build_financial_repository
from backend.services.financials_view_service import (
    CONCEPT_LABELS,
    FinancialsRow,
    FinancialsViewService,
)

TICKERS = ("AAPL", "KO", "JNJ", "JPM")
MAX_YEARS = 10
#: Per-statement quotas: guarantees every sub-tab has content while keeping
#: each fixture under the ~30 KB demo cap (~40 concepts × 10 years). The
#: whole demo bundle stays below its 500 KB guard (test_demo_mode).
QUOTAS = {
    "balance_sheet": 14,
    "income_statement": 10,
    "cash_flow": 10,
    "other": 6,
}
TARGET = REPO_ROOT / "data" / "demo" / "financials"


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


def build_fixture(ticker: str, service: FinancialsViewService) -> dict | None:
    view = service.build(ticker, "FY", MAX_YEARS)
    if view is None:
        return None
    kept = {
        "balance_sheet": _top(view.balance_sheet, QUOTAS["balance_sheet"]),
        "income_statement": _top(view.income_statement, QUOTAS["income_statement"]),
        "cash_flow": _top(view.cash_flow, QUOTAS["cash_flow"]),
        "other": _top(view.other, QUOTAS["other"]),
    }
    total_rows = (
        len(view.balance_sheet)
        + len(view.income_statement)
        + len(view.cash_flow)
        + len(view.other)
    )
    kept_rows = sum(len(rows) for rows in kept.values())
    return {
        "ticker": view.ticker,
        "company_name": view.company_name,
        "fiscal_period": "FY",
        "years": view.years,
        "note": (
            f"Demo fixture: top {kept_rows} of {total_rows} concepts by year "
            f"coverage, {len(view.years)} most recent fiscal years."
        ),
        "balance_sheet": [_row_payload(row) for row in kept["balance_sheet"]],
        "income_statement": [_row_payload(row) for row in kept["income_statement"]],
        "cash_flow": [_row_payload(row) for row in kept["cash_flow"]],
        "other": [_row_payload(row) for row in kept["other"]],
        "unmatched_count": len(kept["other"]),
    }


def main() -> int:
    service = FinancialsViewService(build_financial_repository())
    TARGET.mkdir(parents=True, exist_ok=True)
    for ticker in TICKERS:
        payload = build_fixture(ticker, service)
        if payload is None:
            print(f"{ticker}: no facts stored, skipped")
            continue
        target = TARGET / f"{ticker}.json"
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        rows = sum(
            len(payload[bucket])
            for bucket in (
                "balance_sheet",
                "income_statement",
                "cash_flow",
                "other",
            )
        )
        print(f"{ticker}: {rows} rows, {target.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
