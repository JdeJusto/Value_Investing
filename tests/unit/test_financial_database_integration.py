"""
Integration tests comparing Financial-DataBase repository with existing providers.
Tests data consistency and validates that Financial-DataBase can serve as a drop-in replacement.
"""

import os
from datetime import date

import pytest

from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)
from backend.repositories.financial_repository import SqlAlchemyFinancialRepository


@pytest.mark.integration
class TestFinancialDatabaseIntegration:
    """Integration tests for Financial-DataBase repository."""

    @pytest.fixture
    def financial_db_repo(self) -> FinancialRepository:
        """Create FinancialDatabaseRepository instance."""
        return FinancialDatabaseRepository()

    @pytest.fixture
    def sql_repo(self) -> FinancialRepository:
        """Create existing SQL repository instance."""
        return SqlAlchemyFinancialRepository()

    @pytest.fixture
    def test_ticker(self) -> str:
        """Test ticker symbol."""
        return "AAPL"

    @pytest.fixture
    def test_year(self) -> int:
        """Test fiscal year."""
        return 2023

    def test_repository_availability(
        self, financial_db_repo: FinancialRepository
    ) -> None:
        """Test that Financial-DataBase repository is available."""
        # Skip if database is not available
        if not financial_db_repo.available():
            pytest.skip("Financial-DataBase not available")

        assert financial_db_repo.available() is True

    def test_has_data_method(
        self, financial_db_repo: FinancialRepository, test_ticker: str
    ) -> None:
        """Test has_data method returns boolean."""
        if not financial_db_repo.available():
            pytest.skip("Financial-DataBase not available")

        result = financial_db_repo.has_data(test_ticker)
        assert isinstance(result, bool)
        # For AAPL, we expect True if data exists
        # But we won't assert the value since it depends on data loading

    def test_list_years_method(
        self, financial_db_repo: FinancialRepository, test_ticker: str
    ) -> None:
        """Test list_years method returns list of NormalizedFinancials."""
        if not financial_db_repo.available():
            pytest.skip("Financial-DataBase not available")

        years = financial_db_repo.list_years(test_ticker)
        assert isinstance(years, list)
        # All elements should be NormalizedFinancials
        for year_financials in years:
            assert isinstance(year_financials, NormalizedFinancials)
        # Should be sorted descending by fiscal_year
        if years:
            fiscal_years = [y.fiscal_year for y in years]
            assert fiscal_years == sorted(fiscal_years, reverse=True)

    def test_get_normalized_financials_method(
        self, financial_db_repo: FinancialRepository, test_ticker: str, test_year: int
    ) -> None:
        """Test get_normalized_financials returns NormalizedFinancials or None."""
        if not financial_db_repo.available():
            pytest.skip("Financial-DataBase not available")

        result = financial_db_repo.get_normalized_financials(test_ticker, test_year)
        # Result can be None if no data, or NormalizedFinancials if data exists
        if result is not None:
            assert isinstance(result, NormalizedFinancials)
            assert result.ticker == test_ticker.upper()
            assert result.fiscal_year == test_year

    def test_fiscal_year_end_date_method(
        self, financial_db_repo: FinancialRepository, test_ticker: str, test_year: int
    ) -> None:
        """Test fiscal year end date retrieval (fundamentals-only repository)."""
        if not financial_db_repo.available():
            pytest.skip("Financial-DataBase not available")

        fye = financial_db_repo.get_fiscal_year_end_date(test_ticker, test_year)
        # Either None (no data) or a date near the fiscal year end.
        if fye is not None:
            assert hasattr(fye, "year")
            # AAPL's fiscal year ends in late September, so the FYE must be
            # within a reasonable window of the fiscal year.
            assert fye.year in (test_year - 1, test_year, test_year + 1)

        # Shares outstanding is a fundamental fact and must remain available.
        shares = financial_db_repo.get_shares_outstanding(test_ticker, test_year)
        if shares is not None:
            assert shares > 0

    def test_fiscal_year_end_prefers_bucket_calendar_year(
        self,
        financial_db_repo: FinancialRepository,
    ) -> None:
        """Regression: AAPL's 10-K comparatives were mislabelled under the
        current fiscal_year, and a prior-year comparative with a LONGER annual
        span (FY2023, 370 days vs 363) used to hijack the span-first ordering,
        returning 2023-09-30 for every recent year. The fiscal year end must be
        the bucket's OWN calendar-year end."""
        if not financial_db_repo.available():
            pytest.skip("Financial-DataBase not available")

        got = {
            year: financial_db_repo.get_fiscal_year_end_date("AAPL", year)
            for year in (2023, 2024, 2025)
        }
        assert got[2025] == date(2025, 9, 27)
        assert got[2024] == date(2024, 9, 28)
        assert got[2023] == date(2023, 9, 30)

    def test_repository_exposes_no_price_methods(
        self, financial_db_repo: FinancialRepository
    ) -> None:
        """Prices must NOT be read from Financial-DataBase."""
        assert not hasattr(financial_db_repo, "get_latest_price")
        assert not hasattr(financial_db_repo, "get_prices")
        assert not hasattr(financial_db_repo, "get_historical_valuation_ratios")

    @pytest.mark.skipif(
        not os.getenv("FINANCIAL_DATABASE_URL"),
        reason="Financial-DataBase URL not configured",
    )
    def test_data_consistency_with_existing_repository(
        self,
        financial_db_repo: FinancialRepository,
        sql_repo: FinancialRepository,
        test_ticker: str,
        test_year: int,
    ) -> None:
        """Test that Financial-DataBase data is consistent with existing repository."""
        # Skip if either repository is not available
        if not financial_db_repo.available():
            pytest.skip("Financial-DataBase not available")
        if not sql_repo.available():
            pytest.skip("Existing SQL repository not available")

        # Get data from both repositories
        fd_data = financial_db_repo.get_normalized_financials(test_ticker, test_year)
        sql_data = sql_repo.get_normalized_financials(test_ticker, test_year)

        # If both have data, compare key fields
        if fd_data is not None and sql_data is not None:
            # Compare ticker and year
            assert fd_data.ticker == sql_data.ticker
            assert fd_data.fiscal_year == sql_data.fiscal_year

            # Compare key financial fields with tolerance (5%)
            key_fields = [
                "revenue",
                "net_income",
                "total_assets",
                "total_liabilities",
                "equity",
                "operating_cash_flow",
                "free_cash_flow",
            ]

            for field in key_fields:
                fd_value = getattr(fd_data, field, None)
                sql_value = getattr(sql_data, field, None)

                # Skip if either value is None
                if fd_value is None or sql_value is None:
                    continue

                # Skip if both are zero
                if fd_value == 0 and sql_value == 0:
                    continue

                # Calculate tolerance
                if sql_value != 0:
                    tolerance = abs(fd_value - sql_value) / abs(sql_value)
                    assert tolerance <= 0.05, (
                        f"Field {field} differs by more than 5%: FD={fd_value}, SQL={sql_value}"
                    )
                else:
                    # If SQL value is zero, FD value should also be close to zero
                    assert abs(fd_value) <= 0.05 * max(abs(fd_value), 1), (
                        f"Field {field} should be near zero: FD={fd_value}, SQL={sql_value}"
                    )

    def test_fallback_behavior(self) -> None:
        """Test that repository properly handles unavailable database."""
        # This test verifies the fallback logic in build_financial_repository
        # We'll test by temporarily making the database unavailable

        # Store original environment variable
        original_url = os.getenv("FINANCIAL_DATABASE_URL")

        try:
            # Make database unavailable by setting invalid URL
            os.environ["FINANCIAL_DATABASE_URL"] = (
                "postgresql://invalid:invalid@localhost:5432/nonexistent"
            )

            # Try to create repository - should fall back to SQL or JSON
            repo = FinancialDatabaseRepository()
            # Should not raise exception, but available() should return False
            assert repo.available() is False

        finally:
            # Restore original environment variable
            if original_url is not None:
                os.environ["FINANCIAL_DATABASE_URL"] = original_url
            elif "FINANCIAL_DATABASE_URL" in os.environ:
                del os.environ["FINANCIAL_DATABASE_URL"]

    def test_has_active_listing(self, financial_db_repo) -> None:
        """has_active_listing separates known listings from mapping gaps."""
        if not financial_db_repo.available():
            pytest.skip("Financial-DataBase not available")

        # A well-known active S&P ticker must resolve.
        assert financial_db_repo.has_active_listing("AAPL") is True
        # Garbage symbols are not listed companies -> False (mapping gap).
        assert financial_db_repo.has_active_listing("ZZZZQQ") is False
        # Tickers are matched case-insensitively.
        assert financial_db_repo.has_active_listing("aapl") is True

    @pytest.mark.skipif(
        not os.getenv("FINANCIAL_DATABASE_URL"),
        reason="Financial-DataBase URL not configured",
    )
    def test_staleness_is_consistent_with_and_without_company_scoped_runs(self):
        """The bulk staleness scan may use import_runs.company_id (migration
        0021) but must never report a company as staler than the
        timestamp-only expression, and must fall back to it exactly when a
        company has no scoped run."""
        import psycopg2
        from psycopg2.extras import RealDictCursor

        from backend.services.refresh_service import FdbGateway

        gateway = FdbGateway()
        if not gateway.available():
            pytest.skip("Financial-DataBase unreachable")

        tickers = ["AAPL", "ZZZZQQ", "MSFT"]
        bulk = gateway.staleness_bulk(tickers)
        assert set(bulk) == {t.upper() for t in tickers}

        conn = psycopg2.connect(
            os.environ["FINANCIAL_DATABASE_URL"], cursor_factory=RealDictCursor
        )
        try:
            for ticker in ("AAPL", "MSFT"):
                company_id, _cik, last = bulk[ticker]
                if company_id is None:
                    continue  # unmapped ticker: nothing to compare
                assert last is not None, f"{ticker} has data but no timestamp"
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT GREATEST(
                            (SELECT max(updated_at) FROM financial_facts WHERE company_id = %s),
                            (SELECT max(created_at) FROM filings WHERE company_id = %s),
                            (SELECT updated_at FROM companies WHERE id = %s)
                        ) AS ts_only,
                        (SELECT count(*) FROM import_runs
                          WHERE company_id = %s AND status = 'success') AS scoped_runs
                        """,
                        (company_id, company_id, company_id, company_id),
                    )
                    row = cur.fetchone()
                ts_only, scoped_runs = row["ts_only"], row["scoped_runs"]
                if scoped_runs:
                    # The scoped run can only make the company fresher.
                    assert last >= ts_only
                else:
                    # No scoped run -> exact fallback to the timestamp scan.
                    assert last == ts_only
        finally:
            conn.close()


if __name__ == "__main__":
    # Allow running the test directly for manual verification
    pytest.main([__file__, "-v"])
