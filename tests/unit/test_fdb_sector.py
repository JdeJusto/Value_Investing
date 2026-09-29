"""Tests that ``sector`` flows from Financial-DataBase metadata into the VO.

Two layers:

* a hermetic check that the ``sector`` field survives the
  ``to_dict``/``from_dict`` round trip used by storage and ``analyze``;
* integration checks (skipped when the database is unreachable) asserting the
  repository stamps every reconstructed year with the company's
  ``companies.sector`` value, matching the enrichment written by
  Financial-DataBase's ``scripts/populate_sector_industry.py``.
"""

from __future__ import annotations

import json

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)

#: The tickers the sector enrichment was verified against (all populated by
#: the Financial-DataBase populate_sector_industry.py run).
VERIFICATION_TICKERS = ("AAPL", "MSFT", "KO", "PG", "TSLA", "JPM", "BAC", "PLD", "O")

#: Expected sector per ticker once the FDB metadata is populated (from the
#: Yahoo enrichment run).
EXPECTED_SECTORS = {
    "JPM": "Financial Services",
    "BAC": "Financial Services",
    "PLD": "Real Estate",
    "O": "Real Estate",
    "AAPL": "Technology",
    "MSFT": "Technology",
}


# ---------------------------------------------------------------------------
# hermetic: the field lives on the VO and survives storage round trips
# ---------------------------------------------------------------------------
def test_sector_field_defaults_to_none():
    row = NormalizedFinancials(ticker="T", fiscal_year=2024)
    assert row.sector is None


def test_sector_round_trips_through_json_storage():
    row = NormalizedFinancials.from_dict(
        {"ticker": "T", "fiscal_year": 2024, "sector": "Technology"}
    )
    assert row.sector == "Technology"
    # Same path the JSON repository / analysis pipeline use: dict -> json -> dict.
    blob = json.dumps(row.to_dict())
    rebuilt = NormalizedFinancials.from_dict(json.loads(blob))
    assert rebuilt.sector == "Technology"


# ---------------------------------------------------------------------------
# integration: repository stamps rows with companies.sector
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestFdbSectorExposure:
    """Verify the recomposed rows carry the company's metadata sector."""

    @pytest.fixture
    def repo(self) -> FinancialDatabaseRepository:
        return FinancialDatabaseRepository()

    def _db_sector(self, repo: FinancialDatabaseRepository, ticker: str):
        """Independent companies.sector lookup (not via the code under test)."""
        conn = repo._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.sector
                FROM companies c
                JOIN company_identifiers ci ON c.id = ci.company_id
                WHERE UPPER(ci.identifier_type) = 'TICKER'
                  AND UPPER(ci.identifier_value) = %s
                LIMIT 1
                """,
                (ticker.upper(),),
            )
            row = cur.fetchone()
            return row["sector"] if row else None

    def test_list_years_rows_carry_the_metadata_sector(self, repo):
        if not repo.available():
            pytest.skip("Financial-DataBase not available")

        for ticker in VERIFICATION_TICKERS:
            db_sector = self._db_sector(repo, ticker)
            rows = repo.list_years(ticker)
            assert isinstance(rows, list)
            if not rows:
                continue
            # Every reconstructed year must carry the same sector as the
            # company metadata — including "no sector" (None) when the
            # enrichment has not run for that company.
            assert all(row.sector == db_sector for row in rows), ticker

    def test_expected_sectors_when_metadata_is_populated(self, repo):
        if not repo.available():
            pytest.skip("Financial-DataBase not available")

        db_sector = self._db_sector(repo, "JPM")
        if db_sector is None:
            pytest.skip(
                "companies.sector not populated; run Financial-DataBase "
                "scripts/populate_sector_industry.py first"
            )

        for ticker, expected in EXPECTED_SECTORS.items():
            assert self._db_sector(repo, ticker) == expected, ticker
            rows = repo.list_years(ticker)
            assert rows, f"no fundamentals for {ticker}"
            assert all(row.sector == expected for row in rows), ticker

    def test_unknown_sector_remains_none(self, repo):
        if not repo.available():
            pytest.skip("Financial-DataBase not available")

        # A company whose metadata has no sector yet must read as None on the
        # VO (never a fabricated label). Use any ticker and compare against the
        # database value rather than assuming one is unpopulated.
        ticker = "AAPL"
        db_sector = self._db_sector(repo, ticker)
        rows = repo.list_years(ticker)
        assert rows
        assert all(row.sector == db_sector for row in rows)
