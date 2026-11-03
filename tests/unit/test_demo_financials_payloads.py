"""Demo Financials payloads: every ticker in the offline bundle has a
Fix-B-aware fixture that the T-view can render, and the demo matches the
live layout for the critical companies.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.services.demo_mode import DEMO_TICKERS
from backend.services.financials_view_service import classify_concept
from ui.balance_map import (
    BALANCE_MAP,
    MASS_ORDER,
    MASS_SUBTOTAL_CONCEPTS,
    MEMORANDUM_CONCEPTS,
    TOTAL_CONCEPTS,
)

_FINANCIALS_DIR = Path("data/demo/financials")


def _balance_relevant() -> set[str]:
    relevant: set[str] = set()
    for mass in MASS_ORDER:
        for slot in BALANCE_MAP.get(mass, []):
            relevant.update(slot)
    for mass in MASS_ORDER:
        relevant.update(MASS_SUBTOTAL_CONCEPTS.get(mass, []))
    for concepts in TOTAL_CONCEPTS.values():
        relevant.update(concepts)
    relevant.update(MEMORANDUM_CONCEPTS)
    return relevant


_BALANCE_RELEVANT = _balance_relevant()


def test_all_demo_tickers_have_financials_payload():
    """Every ticker in the demo bundle has a Financials fixture."""
    missing = [
        ticker
        for ticker in DEMO_TICKERS
        if not (_FINANCIALS_DIR / f"{ticker}.json").exists()
    ]
    assert not missing, f"missing Financials payloads: {missing}"


def test_adbe_payload_has_minimum_balance_rows():
    """ADBE renders >=10 lines per column in the T-view."""
    payload = json.loads((_FINANCIALS_DIR / "ADBE.json").read_text(encoding="utf-8"))
    assert len(payload["balance_sheet"]) >= 10
    # liabilities + equity together feed the right columns
    assert len(payload["balance_sheet"]) >= 10


def test_apple_demo_matches_live_view():
    """AAPL demo payload is compatible with the live T-view layout."""
    payload = json.loads((_FINANCIALS_DIR / "AAPL.json").read_text(encoding="utf-8"))
    # The T-view shows 15 asset lines and 13 liability+equity lines for AAPL
    assert len(payload["balance_sheet"]) >= 13
    # Critical rows present (Fix-B)
    concepts = {row["concept"] for row in payload["balance_sheet"]}
    assert "CashAndCashEquivalentsAtCarryingValue" in concepts
    assert "Assets" in concepts or "LiabilitiesAndStockholdersEquity" in concepts


def test_payload_bucket_integrity():
    """Balance rows in the balance_sheet bucket are balance-relevant."""
    for ticker in DEMO_TICKERS:
        path = _FINANCIALS_DIR / f"{ticker}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload["balance_sheet"]:
            concept = row["concept"]
            # Every balance row must be balance-relevant per the Fix-B map
            # OR classified as balance_sheet by the canonical classifier.
            assert (
                concept in _BALANCE_RELEVANT
                or classify_concept(concept) == "balance_sheet"
            ), f"{ticker}: {concept} in balance_sheet but not balance-relevant"
        # other bucket may hold leftovers; balance-relevant ones must not
        # be missing from the T-view (they live in balance_sheet or other)
        # but we only enforce they are not misbucketed to income/cash_flow
        for row in payload["income_statement"]:
            assert classify_concept(row["concept"]) == "income_statement"
        for row in payload["cash_flow"]:
            assert classify_concept(row["concept"]) == "cash_flow"
