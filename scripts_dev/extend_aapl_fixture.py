"""Hand-extend the tracked AAPL demo fixture with real balance-sheet facts.

Adds the face-of-balance-sheet concepts the original "top 32 by coverage"
generator left out (reported totals, non-current mass subtotals, the equity
breakdown, marketable securities and debt) so the T-format balance view and
the "Cuadra" chip render a complete statement in demo mode.

Values are real Financial-DataBase facts resolved with the same
``dedupe_facts`` the live view uses and abbreviated with the backend
formatter, so rows stay byte-compatible with the original generator.
Buckets follow ``classify_concept`` (faithful to live mode) and the script
is idempotent: concepts already present are skipped.

Run:  .venv/bin/python scripts_dev/extend_aapl_fixture.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.services.financials_view_service import (  # noqa: E402
    FinancialsViewService,
    classify_concept,
    dedupe_facts,
    humanize_concept,
)
from backend.services.ui_format import abbreviate_number  # noqa: E402

FIXTURE = (
    Path(__file__).resolve().parents[1] / "data" / "demo" / "financials" / "AAPL.json"
)

#: Face-of-balance-sheet concepts to add (tied to ui/balance_map.py slots).
BALANCE_ADDITIONS = [
    "Assets",
    "AssetsNoncurrent",
    "Liabilities",
    "LiabilitiesNoncurrent",
    "StockholdersEquity",
    "PropertyPlantAndEquipmentNet",
    "LongTermDebtNoncurrent",
    "RetainedEarningsAccumulatedDeficit",
    "NontradeReceivablesCurrent",
    "OtherLiabilitiesCurrent",
]
#: Classified by the backend as "other" but rendered in the T masses.
OTHER_ADDITIONS = [
    "MarketableSecuritiesCurrent",
    "MarketableSecuritiesNoncurrent",
    "LongTermDebtCurrent",
    "CommonStocksIncludingAdditionalPaidInCapital",
]

NOTE_SUFFIX = (
    " Balance sheet extended by hand with real Financial-DataBase facts "
    "(totals, non-current subtotals, equity breakdown, debt and securities) "
    "for the T-format view."
)


def main() -> None:
    payload = json.loads(FIXTURE.read_text())
    years = set(payload["years"])
    service = FinancialsViewService()
    facts = service.fetch_facts(payload["ticker"], payload["fiscal_period"], len(years))
    latest = dedupe_facts(facts, years)

    buckets = ("balance_sheet", "income_statement", "cash_flow", "other")
    existing = {row["concept"] for bucket in buckets for row in payload[bucket]}

    added_count = 0
    for concept in BALANCE_ADDITIONS + OTHER_ADDITIONS:
        if concept in existing:
            continue
        values: dict[str, str] = {}
        unit = ""
        for year in payload["years"]:
            fact = latest.get((concept, year))
            if not fact or fact.get("value") is None:
                continue
            unit = str(fact.get("unit") or "USD")
            values[str(year)] = abbreviate_number(fact["value"], unit)
        if not values:
            print(f"skip {concept}: no facts for {payload['years'][0]}-{payload['years'][-1]}")
            continue
        bucket = classify_concept(concept)
        if bucket not in ("balance_sheet", "other"):
            print(f"skip {concept}: classifies as {bucket}")
            continue
        payload[bucket].append(
            {
                "concept": concept,
                "label": humanize_concept(concept),
                "values": values,
                "unit": unit,
            }
        )
        added_count += 1
        print(f"add  {bucket:16s} {concept} ({len(values)} years)")

    payload["unmatched_count"] = len(payload["other"])
    if NOTE_SUFFIX not in payload.get("note", ""):
        payload["note"] = payload.get("note", "").rstrip() + NOTE_SUFFIX

    FIXTURE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    total = sum(len(payload[bucket]) for bucket in buckets)
    print(f"done: +{added_count} rows, {total} total, unmatched={payload['unmatched_count']}")


if __name__ == "__main__":
    main()
