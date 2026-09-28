"""Integration check for shares outstanding from Financial-DataBase."""

import os

import pytest

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)


def test_shares_outstanding_comes_from_balance_sheet_concepts() -> None:
    """P/E and P/BV use the share count mapped from SEC balance-sheet facts."""
    if not os.environ.get("FINANCIAL_DATABASE_URL"):
        pytest.skip("set FINANCIAL_DATABASE_URL to run this integration test")

    repo = FinancialDatabaseRepository()
    try:
        if not repo.available():
            pytest.fail("Financial-DataBase is not reachable at FINANCIAL_DATABASE_URL")

        rows = repo.get_best_available("AAPL")
        if not rows:
            pytest.skip("AAPL SEC fundamentals are not loaded in the test database")

        assert rows[0].shares_outstanding
        assert rows[0].shares_outstanding > 1_000_000_000
    finally:
        repo.close()
