"""Service for executing reusable SQL scripts from Financial-DataBase."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import psycopg2
import psycopg2.extensions
import sqlparse
from sqlalchemy.exc import SQLAlchemyError

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)


@dataclass
class SqlScriptResult:
    """Result of executing a SQL script."""
    script_name: str
    description: str
    parameters: dict[str, Any]
    rows: list[dict[str, Any]]
    row_count: int
    execution_time_ms: float
    success: bool
    error_message: str | None = None


SCRIPT_ALIASES = {
    "compare": "compare_companies",
}


class SqlAnalysisService:
    """Service for executing reusable SQL scripts from Financial-DataBase."""

    def __init__(self, repository: FinancialDatabaseRepository | None = None):
        """Initialize the SQL analysis service.

        Args:
            repository: FinancialDatabaseRepository instance. If None, creates a new one.
        """
        self._repository = repository or FinancialDatabaseRepository()
        self._scripts_dir = os.path.join(
            os.path.dirname(__file__),
            "../../../Financial-DataBase/scripts"
        )

    def get_available_scripts(self) -> list[dict[str, str]]:
        """Get list of available reusable SQL scripts.

        Returns:
            List of dictionaries containing script information
        """
        scripts = []
        analysis_dir = os.path.join(self._scripts_dir, "analysis")

        if not os.path.exists(analysis_dir):
            return scripts

        for filename in os.listdir(analysis_dir):
            if filename.endswith(".sql"):
                script_path = os.path.join(analysis_dir, filename)
                try:
                    with open(script_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Extract description from comments
                    description = self._extract_description(content)

                    scripts.append({
                        "name": filename[:-4],  # Remove .sql extension
                        "filename": filename,
                        "path": script_path,
                        "description": description or "No description available"
                    })
                except Exception:
                    # Skip files that can't be read
                    continue

        return sorted(scripts, key=lambda x: x["name"])

    def _extract_description(self, content: str) -> str | None:
        """Extract description from SQL script comments.

        Args:
            content: SQL script content

        Returns:
            Description string or None if not found
        """
        lines = content.split('\n')
        for line in lines[:10]:  # Check first 10 lines
            stripped = line.strip()
            if stripped.startswith('--'):
                # Remove leading -- and any extra spaces
                desc = stripped[2:].strip()
                if desc and not desc.lower().startswith('reusable sql script'):
                    return desc
            elif stripped and not stripped.startswith('--'):
                # Stop at first non-comment line
                break
        return None

    def _add_limit_clause(self, sql: str, limit: int | None) -> str:
        """Add a LIMIT clause to a SELECT query if limit is provided.

        Args:
            sql: SQL query string
            limit: Limit value (positive integer) or None

        Returns:
            Modified SQL string with LIMIT clause added if applicable
        """
        if limit is None:
            return sql

        # Check if it's a SELECT query (case-insensitive, ignoring leading whitespace/comments)
        # We'll use a simple heuristic: first non-whitespace characters after optional comments
        # For simplicity, we'll just check if the string, after stripping leading whitespace, starts with SELECT (case-insensitive)
        # This is not perfect but works for our use case.
        stripped_sql = sql.lstrip()
        if stripped_sql.upper().startswith('SELECT'):
            # Remove any trailing semicolon to append LIMIT before it
            has_semicolon = stripped_sql.endswith(';')
            if has_semicolon:
                stripped_sql = stripped_sql[:-1].rstrip()
            # Append LIMIT clause
            return f"{stripped_sql} LIMIT {limit}{';' if has_semicolon else ''}"
        else:
            # Not a SELECT query, ignore limit
            return sql

    def _convert_param_style(self, sql: str) -> str:
        """Convert :param style parameters to %(param)s style for psycopg2.

        The ``::`` cast operator is protected so something like
        ``:ciks::text[]`` becomes ``%(ciks)s::text[]`` and not a broken match.

        Args:
            sql: SQL query string with :param style parameters

        Returns:
            SQL query string with %(param)s style parameters
        """
        import re
        cast_sentinel = "\x00\x00"
        # Protect PostgreSQL :: cast operator from the param regex.
        sql = sql.replace("::", cast_sentinel)
        # Match :param but not an already-converted %(param)s.
        converted = re.sub(
            r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)",
            r"%(\1)s",
            sql,
        )
        return converted.replace(cast_sentinel, "::")

    def execute_script(
        self,
        script_name: str,
        parameters: dict[str, Any] | None = None
    ) -> SqlScriptResult:
        """Execute a reusable SQL script.

        Args:
            script_name: Name of the script (without .sql extension)
            parameters: Dictionary of parameters to bind to the script

        Returns:
            SqlScriptResult containing the execution results
        """
        import time

        if parameters is None:
            parameters = {}

        # Resolve user-friendly script aliases (e.g. 'compare').
        script_name = SCRIPT_ALIASES.get(script_name, script_name)

        # Find the script file
        script_path = os.path.join(self._scripts_dir, "analysis", f"{script_name}.sql")
        if not os.path.exists(script_path):
            return SqlScriptResult(
                script_name=script_name,
                description="Script not found",
                parameters=parameters,
                rows=[],
                row_count=0,
                execution_time_ms=0.0,
                success=False,
                error_message=f"Script '{script_name}' not found in {self._scripts_dir}/analysis/"
            )

        # Read the script content
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
        except Exception as e:
            return SqlScriptResult(
                script_name=script_name,
                description="Failed to read script",
                parameters=parameters,
                rows=[],
                row_count=0,
                execution_time_ms=0.0,
                success=False,
                error_message=f"Could not read script file: {e}"
            )

        # Clean up the SQL (remove extra whitespace, but keep comments for clarity)
        sql_content = sql_content.strip()
        if not sql_content:
            return SqlScriptResult(
                script_name=script_name,
                description="Empty script",
                parameters=parameters,
                rows=[],
                row_count=0,
                execution_time_ms=0.0,
                success=False,
                error_message="Script file is empty"
            )

        # Handle limit parameter: if present and it's a SELECT query, add LIMIT clause
        limit_param = parameters.get('limit')
        if limit_param is not None:
            # Check if we need to add LIMIT clause via string manipulation
            # (if the script doesn't already have a :limit placeholder)
            stripped_sql = sql_content.lstrip()
            has_limit_placeholder = ':limit' in sql_content

            # Skip comments and WITH clauses to find the actual SELECT statement
            # We look for the first non-comment line that starts with SELECT
            lines = stripped_sql.split('\n')
            select_found = False
            for line in lines:
                line_stripped = line.lstrip()
                if line_stripped.startswith('--'):
                    # Skip comment lines
                    continue
                if line_stripped.upper().startswith('SELECT'):
                    select_found = True
                    break
                # If we encounter a line that doesn't start with SELECT or WITH,
                # and it's not a comment, we stop looking
                if line_stripped and not line_stripped.upper().startswith('WITH'):
                    break

            if select_found and not has_limit_placeholder:
                # Remove any trailing semicolon to append LIMIT before it
                has_semicolon = stripped_sql.endswith(';')
                if has_semicolon:
                    stripped_sql = stripped_sql[:-1].rstrip()
                # Append LIMIT clause
                sql_content = f"{stripped_sql} LIMIT {limit_param}{';' if has_semicolon else ''}"
                # Remove limit from parameters since we added it via string manipulation
                # and the script doesn't have a :limit placeholder
                parameters = {k: v for k, v in parameters.items() if k != 'limit'}
            # If the script has a :limit placeholder, we keep the parameter and let _add_limit_clause handle it
            # (though currently _add_limit_clause doesn't handle :limit, we keep the parameter for consistency)

        # Execute the SQL
        start_time = time.time()
        try:
            # Get database connection from repository
            conn = self._repository._get_connection()
            # Use regular cursor to avoid issues with RealDictCursor and named parameters
            with conn.cursor(cursor_factory=psycopg2.extensions.cursor) as cur:
                # Parse and format the SQL
                parsed = sqlparse.parse(sql_content)[0]
                formatted_sql = str(parsed).strip()

                # Convert :param style to %(param)s style for psycopg2
                formatted_sql = self._convert_param_style(formatted_sql)

                # Debug information
                print(f"DEBUG: Executing SQL: {formatted_sql[:200]}...", file=sys.stderr)
                print(f"DEBUG: With parameters: {parameters}", file=sys.stderr)
                print(f"DEBUG: Parameter type: {type(parameters)}", file=sys.stderr)

                # Execute with parameters
                cur.execute(formatted_sql, parameters)

                # Fetch results
                if cur.description:  # Query returns rows
                    # Get column names
                    column_names = [desc[0] for desc in cur.description]
                    rows = []
                    for row in cur.fetchall():
                        row_dict = {}
                        for idx, val in enumerate(row):
                            column_name = column_names[idx]
                            # Convert any non-serializable types
                            if hasattr(val, 'isoformat'):  # datetime objects
                                val = val.isoformat()
                            elif val is None:
                                val = None
                            row_dict[column_name] = val
                        rows.append(row_dict)
                else:
                    rows = []
                    # For non-SELECT statements, get affected row count
                    rows = [{"affected_rows": cur.rowcount}]

                execution_time_ms = (time.time() - start_time) * 1000

                return SqlScriptResult(
                    script_name=script_name,
                    description=self._extract_description(sql_content) or "No description",
                    parameters=parameters,
                    rows=rows,
                    row_count=len(rows),
                    execution_time_ms=execution_time_ms,
                    success=True
                )

        except SQLAlchemyError as e:
            execution_time_ms = (time.time() - start_time) * 1000
            return SqlScriptResult(
                script_name=script_name,
                description="SQL execution error",
                parameters=parameters,
                rows=[],
                row_count=0,
                execution_time_ms=execution_time_ms,
                success=False,
                error_message=str(e)
            )
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            return SqlScriptResult(
                script_name=script_name,
                description="Unexpected error",
                parameters=parameters,
                rows=[],
                row_count=0,
                execution_time_ms=execution_time_ms,
                success=False,
                error_message=str(e)
            )

    def get_company_overview(self, ticker: str) -> SqlScriptResult:
        """Get company overview using the company_overview.sql script.

        Args:
            ticker: Company ticker symbol

        Returns:
            SqlScriptResult with company overview data
        """
        # First get the CIK for the ticker
        try:
            company_id = self._repository._get_company_id_by_ticker(ticker)
            if not company_id:
                return SqlScriptResult(
                    script_name="company_overview",
                    description="Company not found",
                    parameters={"ticker": ticker},
                    rows=[],
                    row_count=0,
                    execution_time_ms=0.0,
                    success=False,
                    error_message=f"Company with ticker '{ticker}' not found"
                )

            # Get the CIK from company_identifiers
            conn = self._repository._get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ci.identifier_value
                    FROM company_identifiers ci
                    JOIN data_providers dp ON ci.provider_id = dp.id
                    WHERE ci.company_id = %s
                      AND ci.identifier_type = 'CIK'
                      AND dp.name = 'SEC EDGAR'
                """, (company_id,))
                row = cur.fetchone()
                if not row:
                    return SqlScriptResult(
                        script_name="company_overview",
                        description="CIK not found for company",
                        parameters={"ticker": ticker},
                        rows=[],
                        row_count=0,
                        execution_time_ms=0.0,
                        success=False,
                        error_message=f"No CIK found for ticker '{ticker}'"
                    )
                cik = row['identifier_value']

                # Execute the company_overview script
                return self.execute_script("company_overview", {"cik": cik})

        except Exception as e:
            return SqlScriptResult(
                script_name="company_overview",
                description="Failed to get company overview",
                parameters={"ticker": ticker},
                rows=[],
                row_count=0,
                execution_time_ms=0.0,
                success=False,
                error_message=str(e)
            )


def get_sql_analysis_service() -> SqlAnalysisService:
    """Get or create a SQL analysis service instance.

    Returns:
        SqlAnalysisService instance
    """
    return SqlAnalysisService()


if __name__ == "__main__":
    # Simple test
    service = SqlAnalysisService()
    print("Available scripts:")
    for script in service.get_available_scripts():
        print(f"  - {script['name']}: {script['description']}")

    # Test company overview if we have a repository
    try:
        repo = FinancialDatabaseRepository()
        if repo.available():
            print("\nTesting company overview for AAPL:")
            result = service.get_company_overview("AAPL")
            if result.success:
                print(f"Found {result.row_count} rows")
                for row in result.rows[:3]:  # Show first 3 rows
                    print(f"  {row}")
            else:
                print(f"Error: {result.error_message}")
        else:
            print("\nFinancial-DataBase repository not available")
    except Exception as e:
        print(f"\nError initializing repository: {e}")