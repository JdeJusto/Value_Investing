"""
Unit tests for compare_sources.py script.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add the scripts directory to the path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../scripts'))

from compare_sources import compare_financials, main


class TestCompareSources:
    """Test compare_sources functionality."""

    @pytest.fixture
    def mock_fd_repo(self):
        """Create a mock Financial-DataBase repository."""
        repo = Mock()
        repo.available.return_value = True
        # Mock financial data objects
        financials = Mock()
        financials.fiscal_year = 2023
        financials.revenue = 10000000000  # 10B
        financials.net_income = 1000000000  # 1B
        financials.total_assets = 50000000000  # 50B
        financials.total_liabilities = 30000000000  # 30B
        financials.operating_cash_flow = 2000000000  # 2B
        financials.capital_expenditure = 500000000  # 500M
        financials.shareholders_equity = 20000000000  # 20B
        financials.diluted_eps = 5.0
        financials.free_cash_flow = 1500000000  # 1.5B
        older = Mock()
        older.fiscal_year = 2022
        older.revenue = 9000000000
        older.net_income = 900000000
        older.total_assets = 45000000000
        older.total_liabilities = 27000000000
        older.operating_cash_flow = 1800000000
        older.capital_expenditure = 400000000
        older.shareholders_equity = 18000000000
        older.diluted_eps = 4.5
        older.free_cash_flow = 1400000000
        repo.list_years.return_value = [financials, older]
        # The most recent completed fiscal year is 2023.
        repo.get_latest_completed_fiscal_year.return_value = 2023
        repo.get_latest_financials.return_value = financials
        return repo

    @pytest.fixture
    def mock_yahoo_provider(self):
        """Create a mock Yahoo Finance provider."""
        provider = Mock()
        # Income statement
        income = Mock()
        income.revenue = 10500000000  # 10.5B (5% difference)
        income.net_income = 950000000  # 0.95B (5% difference)
        provider.get_income_statement.return_value = income
        # Balance sheet
        balance = Mock()
        balance.total_assets = 52000000000  # 52B
        balance.total_liabilities = 28000000000  # 28B
        balance.stockholders_equity = 22000000000  # 22B
        provider.get_balance_sheet.return_value = balance
        # Cash flow
        cash_flow = Mock()
        cash_flow.operating_cash_flow = 2100000000  # 2.1B
        cash_flow.capital_expenditure = 450000000  # 450M
        cash_flow.free_cash_flow = 1600000000  # 1.6B
        provider.get_cash_flow.return_value = cash_flow
        # Shares outstanding
        provider.get_shares_outstanding.return_value = 200000000  # 200M shares
        # Fiscal years
        provider.get_fiscal_years.return_value = [2023]
        return provider

    @pytest.fixture
    def mock_edgar_provider(self):
        """Create a mock EDGAR provider."""
        provider = Mock()
        # Income statement
        income = Mock()
        income.revenue = 9800000000  # 9.8B
        income.net_income = 1020000000  # 1.02B
        provider.get_income_statement.return_value = income
        # Balance sheet
        balance = Mock()
        balance.total_assets = 49000000000  # 49B
        balance.total_liabilities = 31000000000  # 31B
        balance.stockholders_equity = 19000000000  # 19B
        provider.get_balance_sheet.return_value = balance
        # Cash flow
        cash_flow = Mock()
        cash_flow.operating_cash_flow = 1900000000  # 1.9B
        cash_flow.capital_expenditure = 550000000  # 550M
        cash_flow.free_cash_flow = 1400000000  # 1.4B
        provider.get_cash_flow.return_value = cash_flow
        # EDGAR provider doesn't have shares_outstanding or fiscal years methods used in our code?
        # We don't call them, so we can leave them unmocked or return None.
        return provider

    @patch('compare_sources.build_financial_repository')
    @patch('compare_sources.YahooFinanceProvider')
    @patch('compare_sources.EdgarProvider')
    def test_compare_financials_all_sources_available(self, mock_edgar, mock_yahoo, mock_build_repo,
                                                      mock_fd_repo, mock_yahoo_provider, mock_edgar_provider):
        """Test comparison when all sources are available."""
        mock_build_repo.return_value = mock_fd_repo
        mock_yahoo.return_value = mock_yahoo_provider
        mock_edgar.return_value = mock_edgar_provider

        # Capture print output
        with patch('builtins.print') as mock_print:
            compare_financials('AAPL')

            # Verify that print was called multiple times (for headers, table, etc.)
            assert mock_print.call_count > 10

            # Check that the comparison table was printed
            print_calls = [str(call) for call in mock_print.call_args_list]
            assert any('Comparing financial data for AAPL' in call for call in print_calls)
            assert any('Revenue' in call for call in print_calls)
            assert any('Financial-DataBase' in call for call in print_calls)
            assert any('Yahoo Finance' in call for call in print_calls)
            assert any('EDGAR' in call for call in print_calls)

    @patch('compare_sources.build_financial_repository')
    def test_compare_financials_fd_unavailable(self, mock_build_repo):
        """Test comparison when Financial-DataBase is unavailable."""
        mock_build_repo.return_value.available.return_value = False

        with patch('builtins.print') as mock_print:
            compare_financials('AAPL')

            # Should print error message
            print_calls = [str(call) for call in mock_print.call_args_list]
            assert any('ERROR: Financial-DataBase repository not available' in call for call in print_calls)

    @patch('compare_sources.build_financial_repository')
    @patch('compare_sources.YahooFinanceProvider')
    @patch('compare_sources.EdgarProvider')
    def test_compare_financials_no_data_anywhere(self, mock_edgar, mock_yahoo, mock_build_repo):
        """Test comparison when no data is available from any source."""
        mock_fd_repo = Mock()
        mock_fd_repo.available.return_value = True
        mock_fd_repo.list_years.return_value = []  # No years
        mock_build_repo.return_value = mock_fd_repo

        mock_yahoo.side_effect = Exception("Yahoo Finance error")
        mock_edgar.side_effect = Exception("EDGAR error")

        with patch('builtins.print') as mock_print:
            compare_financials('INVALID')

            # Should print error about no data
            print_calls = [str(call) for call in mock_print.call_args_list]
            assert any('ERROR: No financial data available from any source' in call for call in print_calls)

    @patch('compare_sources.build_financial_repository')
    @patch('compare_sources.YahooFinanceProvider')
    @patch('compare_sources.EdgarProvider')
    def test_compare_financials_significant_discrepancies(self, mock_edgar, mock_yahoo, mock_build_repo,
                                                          mock_fd_repo, mock_yahoo_provider, mock_edgar_provider):
        """Test that significant discrepancies are flagged."""
        mock_build_repo.return_value = mock_fd_repo
        mock_yahoo.return_value = mock_yahoo_provider
        mock_edgar.return_value = mock_edgar_provider

        with patch('builtins.print') as mock_print:
            compare_financials('AAPL')

            # Check for discrepancy reporting
            print_calls = [str(call) for call in mock_print.call_args_list]
            assert any('Significant discrepancies' in call for call in print_calls)
            # Should find discrepancies for revenue, net_income, etc. (>5% difference)

    @patch('sys.argv', ['compare_sources.py', 'AAPL', 'MSFT'])
    @patch('compare_sources.compare_financials')
    def test_main_function(self, mock_compare):
        """Test the main function."""
        main()
        # Should be called once for each ticker
        assert mock_compare.call_count == 2
        mock_compare.assert_any_call('AAPL', 'both')
        mock_compare.assert_any_call('MSFT', 'both')


if __name__ == "__main__":
    pytest.main([__file__])