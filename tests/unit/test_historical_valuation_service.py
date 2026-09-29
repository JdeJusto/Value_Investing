"""
Unit tests for HistoricalValuationService (real-time prices + fundamentals).
"""

from unittest.mock import Mock, patch

import pytest

from backend.services.historical_valuation_service import HistoricalValuationService


def _financials(year, net_income, free_cash_flow):
    """Build a NormalizedFinancials-like mock."""
    mock = Mock()
    mock.fiscal_year = year
    mock.net_income = net_income
    mock.free_cash_flow = free_cash_flow
    return mock


class TestHistoricalValuationService:
    """Test HistoricalValuationService class."""

    @pytest.fixture
    def service(self):
        """Create a HistoricalValuationService with mocked deps."""
        with (
            patch("backend.services.historical_valuation_service.FinancialDatabaseRepository"),
            patch("backend.services.historical_valuation_service.PriceService"),
        ):
            return HistoricalValuationService()

    @pytest.fixture
    def mock_repo(self):
        """Create a mock financial repository."""
        return Mock()

    @pytest.fixture
    def mock_prices(self):
        """Create a mock price service."""
        mock = Mock()
        mock.get_split_adjustment.return_value = 1.0
        return mock

    def test_init(self, service):
        """Test service initialization."""
        assert service is not None
        assert hasattr(service, '_repository')
        assert hasattr(service, '_price_service')

    def test_get_historical_valuation_summary_success(self, service, mock_repo, mock_prices):
        """Test successful historical valuation summary retrieval."""
        mock_repo.list_years.return_value = [
            _financials(2023, 96_995_000_000, 99_584_000_000),
            _financials(2022, 99_803_000_000, 111_439_000_000),
        ]
        mock_repo.get_shares_outstanding.side_effect = [
            15_744_231_000,
            16_215_963_000,
        ]
        mock_repo.get_fiscal_year_end_date.return_value = None
        mock_prices.get_price_at_fiscal_year_end.side_effect = [192.53, 129.93]

        with (
            patch.object(service, '_repository', mock_repo),
            patch.object(service, '_price_service', mock_prices),
        ):
            result = service.get_historical_valuation_summary('AAPL')

        assert len(result) == 2
        assert result[0]['fiscal_year'] == 2023
        assert result[0]['price'] == 192.53
        # EPS = net_income / shares
        assert result[0]['eps'] == pytest.approx(96_995_000_000 / 15_744_231_000)
        # P/E = price / eps
        assert result[0]['pe_ratio'] == pytest.approx(
            192.53 / (96_995_000_000 / 15_744_231_000)
        )
        # market cap = price * shares
        assert result[0]['market_cap'] == pytest.approx(192.53 * 15_744_231_000)
        # FCF yield = fcf / market cap
        assert result[0]['fcf_yield'] == pytest.approx(
            99_584_000_000 / (192.53 * 15_744_231_000)
        )
        # Sorted descending by year
        assert [r['fiscal_year'] for r in result] == [2023, 2022]

    def test_get_historical_valuation_summary_missing_price(self, service, mock_repo, mock_prices):
        """Test that a missing price yields N/A rows instead of failing."""
        mock_repo.list_years.return_value = [
            _financials(2023, 96_995_000_000, 99_584_000_000)
        ]
        mock_repo.get_shares_outstanding.return_value = 15_744_231_000
        mock_prices.get_price_at_fiscal_year_end.return_value = None

        with (
            patch.object(service, '_repository', mock_repo),
            patch.object(service, '_price_service', mock_prices),
        ):
            result = service.get_historical_valuation_summary('AAPL')

        assert len(result) == 1
        assert result[0]['price'] is None
        assert result[0]['pe_ratio'] is None
        assert result[0]['fcf_yield'] is None
        assert result[0]['shares_outstanding'] == 15_744_231_000

    def test_get_historical_valuation_summary_repo_error(self, service, mock_repo):
        """Test handling of repository exceptions."""
        mock_repo.list_years.side_effect = Exception("Database error")

        with patch.object(service, '_repository', mock_repo):
            result = service.get_historical_valuation_summary('AAPL')

        assert result == []

    def test_split_adjustment_applied(self, service, mock_repo, mock_prices):
        """Test that historical per-share metrics adjust for stock splits."""
        from datetime import date

        mock_repo.list_years.return_value = [
            _financials(2023, 96_995_000_000, 99_584_000_000)
        ]
        mock_repo.get_shares_outstanding.return_value = 15_744_231_000
        mock_repo.get_fiscal_year_end_date.return_value = date(2023, 9, 30)
        mock_prices.get_price_at_fiscal_year_end.return_value = 192.53
        # Simulate a 4:1 split happening after the fiscal year end.
        mock_prices.get_split_adjustment.return_value = 4.0

        with (
            patch.object(service, '_repository', mock_repo),
            patch.object(service, '_price_service', mock_prices),
        ):
            result = service.get_historical_valuation_summary('AAPL')

        adjusted_shares = 15_744_231_000 * 4.0
        assert result[0]['split_adjustment'] == 4.0
        assert result[0]['eps'] == pytest.approx(96_995_000_000 / adjusted_shares)
        assert result[0]['market_cap'] == pytest.approx(192.53 * adjusted_shares)
        assert result[0]['pe_ratio'] == pytest.approx(
            192.53 / (96_995_000_000 / adjusted_shares)
        )
        assert result[0]['fcf_yield'] == pytest.approx(99_584_000_000 / (192.53 * adjusted_shares))

    def test_get_historical_pe_ratios_and_fcf_yields(self, service, mock_repo, mock_prices):
        """Test the P/E and FCF yield projection helpers."""
        mock_repo.list_years.return_value = [
            _financials(2023, 96_995_000_000, 99_584_000_000)
        ]
        mock_repo.get_shares_outstanding.return_value = 15_744_231_000
        mock_repo.get_fiscal_year_end_date.return_value = None
        mock_prices.get_price_at_fiscal_year_end.return_value = 192.53

        with (
            patch.object(service, '_repository', mock_repo),
            patch.object(service, '_price_service', mock_prices),
        ):
            pe_ratios = service.get_historical_pe_ratios('AAPL')
            fcf_yields = service.get_historical_fcf_yields('AAPL')

        assert 'pe_ratio' in pe_ratios[0]
        assert pe_ratios[0]['pe_ratio'] is not None
        assert 'fcf_yield' in fcf_yields[0]
        assert fcf_yields[0]['fcf_yield'] is not None

    def test_format_valuation_table(self, service, mock_repo, mock_prices):
        """Test formatting valuation data as a table with N/A handling."""
        mock_repo.list_years.return_value = [
            _financials(2023, 96_995_000_000, 99_584_000_000),
            _financials(2022, 99_803_000_000, 111_439_000_000),
        ]
        mock_repo.get_shares_outstanding.side_effect = [
            15_744_231_000,
            16_215_963_000,
        ]
        mock_repo.get_fiscal_year_end_date.return_value = None
        mock_prices.get_price_at_fiscal_year_end.side_effect = [192.53, None]

        with (
            patch.object(service, '_repository', mock_repo),
            patch.object(service, '_price_service', mock_prices),
        ):
            table_output = service.format_valuation_table('AAPL')

        assert '2023' in table_output
        assert '2022' in table_output
        assert '192.53' in table_output
        # Second year has no price — must render N/A gracefully.
        assert 'N/A' in table_output

    def test_format_valuation_table_empty(self, service):
        """Test formatting empty valuation data."""
        with patch.object(service, 'get_historical_valuation_summary') as mock_summary:
            mock_summary.return_value = []

            table_output = service.format_valuation_table('AAPL')

            assert 'No valuation data available for AAPL' in table_output

    def test_format_valuation_table_error(self, service, mock_repo):
        """Test formatting when no financial data exists."""
        mock_repo.list_years.return_value = []

        with patch.object(service, '_repository', mock_repo):
            table_output = service.format_valuation_table('AAPL')

        assert 'No valuation data available for AAPL' in table_output

    def test_skips_all_empty_latest_year(self, service, mock_repo, mock_prices):
        """A stray fiscal-year bucket (no data) must not appear as latest.

        Regression: an in-progress/stray FY2026 bucket carrying only fee/8-K
        facts used to be served as the newest valuation row, so the CLI's
        "latest year" read displayed FY2026 instead of the real FY2025.
        """
        empty = Mock()
        empty.fiscal_year = 2026
        empty.revenue = None
        empty.net_income = None
        empty.total_assets = None
        empty.shares_outstanding = None

        mock_repo.list_years.return_value = [
            empty,
            _financials(2025, 100_000_000_000, 25_000_000_000),
        ]
        mock_repo.get_shares_outstanding.return_value = 10_000_000_000
        mock_prices.get_price_at_fiscal_year_end.return_value = 200.0

        with (
            patch.object(service, '_repository', mock_repo),
            patch.object(service, '_price_service', mock_prices),
        ):
            result = service.get_historical_valuation_summary('AAPL')

        assert [r['fiscal_year'] for r in result] == [2025]
        assert result[0]['price'] == 200.0

    def test_row_is_empty(self, service):
        """The empty-row predicate mirrors the repository's core-field rule."""
        empty = Mock()
        empty.revenue = None
        empty.net_income = None
        empty.total_assets = None
        empty.shares_outstanding = None
        assert service._row_is_empty(empty)

        partial = Mock()
        partial.revenue = 100.0  # one core field populated → usable
        partial.net_income = None
        partial.total_assets = None
        partial.shares_outstanding = None
        assert not service._row_is_empty(partial)


if __name__ == "__main__":
    pytest.main([__file__])
