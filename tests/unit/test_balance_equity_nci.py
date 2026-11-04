"""Regression tests for the NCI-inclusive equity subtotal (AUDIT-001).

FDB 0.2.1 maps ``StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest``
to ``stockholders_equity``. These tests assert the CLI financials view
recognizes that tag as a reported equity subtotal instead of falling back to
``RetainedEarnings`` and flagging partial equity.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)

LARGE_CAPS = ["JNJ", "CAT", "T", "VZ", "CSX", "ADM", "PG"]


def _fdb_available() -> bool:
    try:
        return FinancialDatabaseRepository().available()
    except Exception:  # noqa: BLE001 — no database means skip, not fail
        return False


pytestmark = pytest.mark.skipif(
    not _fdb_available(),
    reason="Financial-DataBase is not reachable",
)


def _financials_json(ticker: str) -> dict:
    result = subprocess.run(
        ["./vi", "financials", ticker, "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("ticker", LARGE_CAPS)
def test_large_cap_equity_is_reported_not_derived(ticker):
    data = _financials_json(ticker)
    eq = data["liabilities_equity"].get("total_equity")
    assert eq is not None, ticker
    assert eq > 0, f"{ticker}: equity must be positive, got {eq}"
    assert data["derived"]["equity"] is False, (
        f"{ticker}: equity is reported via the NCI tag, must not be derived"
    )


@pytest.mark.parametrize("ticker", LARGE_CAPS)
def test_large_cap_balance_balanced(ticker):
    data = _financials_json(ticker)
    assets = data["assets"]["total"]
    liab_eq = data["liabilities_equity"]["total"]
    assert assets, ticker
    assert abs(assets - liab_eq) / abs(assets) < 0.01, (
        f"{ticker}: assets {assets:.2e} vs L+E {liab_eq:.2e}"
    )
