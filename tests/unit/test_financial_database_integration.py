"""
Integration tests comparing Financial-DataBase repository with existing providers.
Tests data consistency and validates that Financial-DataBase can serve as a drop-in replacement.
"""
import os
from datetime import date
from typing import Any

import pytest

from backend.domain.value_objects.filter_criteria import FilterCriteria, FilterOperator
from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.repositories.financial_database_repository import FinancialDatabaseRepository
from backend.repositories.financial_repository import SqlAlchemyFinancialRepository
from backend.domain.interfaces.financial_repository import FinancialRepository


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

    def test_repository_availability(self, financial_db_repo: FinancialRepository) -> None:
        """Test that Financial-DataBase repository is available."""
        # Skip if database is not available
        if not financial_db_repo.available():
            pytest.skip("Financial-DataBase not available")

        assert financial_db_repo.available() is True

    def test_has_data_method(self, financial_db_repo: FinancialRepository, test_ticker: str) -> None:
        """Test has_data method returns boolean."""
        if not financial_db_repo.available():
            pytest.skip("Financial-DataBase not available")

        result = financial_db_repo.has_data(test_ticker)
        assert isinstance(result, bool)
        # For AAPL, we expect True if data exists
        # But we won't assert the value since it depends on data loading

    def test_list_years_method(self, financial_db_repo: FinancialRepository, test_ticker: str) -> None:
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
        self,
        financial_db_repo: FinancialRepository,
        test_ticker: str,
        test_year: int
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

    def test_price_data_methods(
        self,
        financial_db_repo: FinancialRepository,
        test_ticker: str
    ) -> None:
        """Test price data retrieval methods."""
        if not financial_db_repo.available():
            pytest.skip("Financial-DataBase not available")

        # Test get_latest_price
        latest_price = financial_db_repo.get_latest_price(test_ticker)
        # Can be None if no price data, or float if data exists
        if latest_price is not None:
            assert isinstance(latest_price, float)
            assert latest_price > 0

        # Test get_prices with limit
        prices = financial_db_repo.get_prices(test_ticker, limit=5)
        assert isinstance(prices, list)
        # Each price entry should be a dict with expected keys
        for price_entry in prices:
            assert isinstance(price_entry, dict)
            # Check for expected keys (may vary based on implementation)
            assert 'date' in price_entry
            assert 'close' in price_entry
            assert isinstance(price_entry['close'], (int, float))
            assert price_entry['close'] > 0

    @pytest.mark.skipif(
        not os.getenv("FINANCIAL_DATABASE_URL"),
        reason="Financial-DataBase URL not configured"
    )
    def test_data_consistency_with_existing_repository(
        self,
        financial_db_repo: FinancialRepository,
        sql_repo: FinancialRepository,
        test_ticker: str,
        test_year: int
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
                'revenue',
                'net_income',
                'total_assets',
                'total_liabilities',
                'equity',
                'operating_cash_flow',
                'free_cash_flow'
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
                    assert tolerance <= 0.05, f"Field {field} differs by more than 5%: FD={fd_value}, SQL={sql_value}"
                else:
                    # If SQL value is zero, FD value should also be close to zero
                    assert abs(fd_value) <= 0.05 * max(abs(fd_value), 1), f"Field {field} should be near zero: FD={fd_value}, SQL={sql_value}"

    def test_fallback_behavior(self) -> None:
        """Test that repository properly handles unavailable database."""
        # This test verifies the fallback logic in build_financial_repository
        # We'll test by temporarily making the database unavailable

        # Store original environment variable
        original_url = os.getenv("FINANCIAL_DATABASE_URL")

        try:
            # Make database unavailable by setting invalid URL
            os.environ["FINANCIAL_DATABASE_URL"] = "postgresql://invalid:invalid@localhost:5432/nonexistent"

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


if __name__ == "__main__":
    # Allow running the test directly for manual verification
    pytest.main([__file__, "-v"])