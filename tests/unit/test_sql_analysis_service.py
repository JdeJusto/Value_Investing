"""
Unit tests for SqlAnalysisService.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from backend.services.sql_analysis_service import SqlAnalysisService


class TestSqlAnalysisService:
    """Test SqlAnalysisService class."""

    @pytest.fixture
    def service(self):
        """Create a SqlAnalysisService instance."""
        with patch('backend.services.sql_analysis_service.FinancialDatabaseRepository'):
            return SqlAnalysisService()

    @pytest.fixture
    def mock_repo(self):
        """Create a mock financial database repository."""
        return Mock()

    @pytest.fixture
    def service_with_mock_repo(self, mock_repo):
        """Create a SqlAnalysisService instance with mocked repository."""
        service = SqlAnalysisService(mock_repo)
        # Mock the scripts directory to avoid filesystem access
        service._scripts_dir = "/fake/path/to/Financial-DataBase/scripts"
        return service

    def test_init(self, service):
        """Test service initialization."""
        assert service is not None
        assert hasattr(service, '_repository')
        assert hasattr(service, '_scripts_dir')

    def test_get_available_scripts_no_directory(self, service_with_mock_repo):
        """Test getting available scripts when directory doesn't exist."""
        with patch('os.path.exists', return_value=False):
            scripts = service_with_mock_repo.get_available_scripts()
            assert scripts == []

    def test_get_available_scripts_empty_directory(self, service_with_mock_repo):
        """Test getting available scripts when directory is empty."""
        with patch('os.path.exists', return_value=True):
            with patch('os.listdir', return_value=[]):
                scripts = service_with_mock_repo.get_available_scripts()
                assert scripts == []

    def test_get_available_scripts_with_files(self, service_with_mock_repo):
        """Test getting available scripts with SQL files."""
        with patch('os.path.exists', return_value=True):
            with patch('os.listdir', return_value=['company_overview.sql', 'ratios.sql', 'README.md']):
                with patch('builtins.open') as mock_open:
                    mock_open.return_value.__enter__.return_value.read.side_effect = [
                        "-- Description: Company overview\nSELECT 1",
                        "-- Description: Financial ratios\nSELECT 2",
                        "Not a SQL file"
                    ]
                    with patch('os.path.join', side_effect=lambda *args: '/'.join(args)):
                        scripts = service_with_mock_repo.get_available_scripts()
                        assert len(scripts) == 2
                        assert scripts[0]['name'] == 'company_overview'
                        assert scripts[0]['description'] == 'Description: Company overview'
                        assert scripts[1]['name'] == 'ratios'
                        assert scripts[1]['description'] == 'Description: Financial ratios'

    def test_extract_description(self, service_with_mock_repo):
        """Test extracting description from SQL content."""
        # Test normal comment
        content = "-- Description: This is a test script\nSELECT 1;"
        desc = service_with_mock_repo._extract_description(content)
        assert desc == "Description: This is a test script"

        # Test comment without Description prefix
        content = "-- This is a test script\nSELECT 1;"
        desc = service_with_mock_repo._extract_description(content)
        assert desc == "This is a test script"

        # Test no description
        content = "SELECT 1;"
        desc = service_with_mock_repo._extract_description(content)
        assert desc is None

        # Test empty content
        content = ""
        desc = service_with_mock_repo._extract_description(content)
        assert desc is None

    def test_execute_script_not_found(self, service_with_mock_repo):
        """Test executing a non-existent script."""
        result = service_with_mock_repo.execute_script("nonexistent")
        assert result.success == False
        assert "not found" in result.error_message
        assert result.script_name == "nonexistent"

    def test_execute_script_empty_file(self, service_with_mock_repo):
        """Test executing an empty script file."""
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open') as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = ""
                result = service_with_mock_repo.execute_script("empty")
                assert result.success == False
                assert "empty" in result.error_message

    def test_get_company_overview_not_found(self, service_with_mock_repo):
        """Test company overview when ticker not found."""
        service_with_mock_repo._repository._get_company_id_by_ticker.return_value = None

        result = service_with_mock_repo.get_company_overview("INVALID")

        assert result.success == False
        assert "not found" in result.error_message
        assert result.script_name == "company_overview"

    def test_get_company_overview_no_cik(self, service_with_mock_repo):
        """Test company overview when CIK not found."""
        service_with_mock_repo._repository._get_company_id_by_ticker.return_value = 123

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.execute.return_value = None  # Execute returns nothing
        mock_cursor.fetchone.return_value = None  # No CIK found (fetchone returns None)
        mock_cursor.fetchall.return_value = []  # fetchall returns empty list
        mock_cursor.description = None  # No rows returned

        # Mock the context manager properly
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        # Set up the connection mock
        mock_conn.cursor.return_value = mock_cursor
        service_with_mock_repo._repository._get_connection.return_value = mock_conn

        result = service_with_mock_repo.get_company_overview("AAPL")

        assert result.success == False
        assert "No CIK found for ticker 'AAPL'" in result.error_message

    def test_get_sql_analysis_service(self):
        """Test the factory function."""
        with patch('backend.services.sql_analysis_service.SqlAnalysisService') as mock_service_class:
            mock_instance = Mock()
            mock_service_class.return_value = mock_instance

            from backend.services.sql_analysis_service import get_sql_analysis_service
            service = get_sql_analysis_service()

            assert service == mock_instance
            mock_service_class.assert_called_once()

    def test_convert_param_style_basic(self, service_with_mock_repo):
        """Test conversion of :param to %(param)s."""
        sql = "WHERE ci.identifier_value = :cik"
        converted = service_with_mock_repo._convert_param_style(sql)
        assert converted == "WHERE ci.identifier_value = %(cik)s"

    def test_convert_param_style_keeps_cast_operator(self, service_with_mock_repo):
        """Test that :ciks::text[] becomes %(ciks)s::text[]."""
        sql = "SELECT unnest(:ciks::text[]) as cik"
        converted = service_with_mock_repo._convert_param_style(sql)
        assert converted == "SELECT unnest(%(ciks)s::text[]) as cik"

    def test_convert_param_style_idempotent(self, service_with_mock_repo):
        """Test that already-converted SQL is left untouched."""
        sql = "WHERE ci.identifier_value = %(cik)s"
        converted = service_with_mock_repo._convert_param_style(sql)
        assert converted == sql

    def test_script_alias_resolution(self, service_with_mock_repo):
        """Test that 'compare' resolves to 'compare_companies'."""
        from backend.services.sql_analysis_service import SCRIPT_ALIASES
        assert SCRIPT_ALIASES["compare"] == "compare_companies"

    def test_execute_script_passes_list_param(self, service_with_mock_repo):
        """Test that a ciks list is passed through to the DB cursor."""
        service_with_mock_repo._scripts_dir = "/fake/scripts"
        script_content = "SELECT unnest(:ciks::text[]) as cik"

        with patch('os.path.exists', return_value=True):
            with patch('builtins.open') as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = script_content
                # Mock the DB pieces used by execute_script.
                conn = MagicMock()
                cur = MagicMock()
                cur.description = [["cik"]]
                cur.fetchall.return_value = [("0000320193",)]
                cur.__enter__.return_value = cur
                conn.cursor.return_value = cur
                service_with_mock_repo._repository._get_connection.return_value = conn

                result = service_with_mock_repo.execute_script(
                    "compare", {"ciks": ["0000320193", "0000789019"]}
                )

        assert result.success is True
        assert result.script_name == "compare_companies"
        # The executed SQL must contain the converted placeholder.
        executed_sql = cur.execute.call_args[0][0]
        assert "%(ciks)s::text[]" in executed_sql
        # The params dict must carry the list unchanged.
        executed_params = cur.execute.call_args[0][1]
        assert executed_params["ciks"] == ["0000320193", "0000789019"]


if __name__ == "__main__":
    pytest.main([__file__])