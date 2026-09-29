"""SQL analysis command for running Financial-DataBase reusable SQL scripts."""

from __future__ import annotations

import json
import sys

from backend.services.sql_analysis_service import SCRIPT_ALIASES, SqlAnalysisService
from cli.formatters import (
    green,
    print_header,
    red,
    yellow,
)


def register(subparsers):
    """Register the sql-analysis command."""
    p = subparsers.add_parser(
        "sql-analysis",
        help="Run reusable SQL scripts from Financial-DataBase",
        description=(
            "Executes reusable SQL scripts from Financial-DataBase's scripts/analysis directory. "
            "Supports company overview, financial ratios, and other analytical queries."
        ),
    )
    p.add_argument(
        "script",
        nargs="?",
        default=None,
        help="Name of the SQL script to run (without .sql extension, e.g: company_overview, ratios_advanced)",
    )
    p.add_argument(
        "--script",
        dest="script_opt",
        default=None,
        help="Script name as a flag (alternative to the positional argument)",
    )
    p.add_argument(
        "--ticker",
        type=str,
        help="Ticker symbol to use as parameter (for scripts that require a CIK parameter)",
    )
    p.add_argument(
        "--cik",
        type=str,
        help="CIK to use as parameter directly (alternative to --ticker)",
    )
    p.add_argument(
        "--ciks",
        type=str,
        help="Comma-separated list of CIKs (for scripts that accept a CIK array, e.g: compare)",
    )
    p.add_argument(
        "--params",
        type=str,
        help="Additional parameters as JSON string (e.g: '{\"param1\": \"value1\"}')",
    )
    p.add_argument(
        "--limit",
        type=int,
        help="Limit the number of rows returned (for SELECT scripts)",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="List available SQL scripts",
    )
    p.add_argument(
        "--output",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    p.set_defaults(func=_run)


def _run(args):
    """Run the sql-analysis command."""
    service = SqlAnalysisService()

    if args.list:
        _list_scripts(service)
        return

    script_name = (args.script or args.script_opt or "").strip()
    script_name = SCRIPT_ALIASES.get(script_name, script_name)

    if not script_name:
        print(f"{red('ERROR:')} Script name is required")
        return

    # Parse additional parameters
    parameters = {}
    if args.params:
        try:
            parameters = json.loads(args.params)
        except json.JSONDecodeError as e:
            print(f"{red('ERROR:')} Invalid JSON in --params: {e}")
            return

    # Handle --ciks list parameter
    if args.ciks:
        raw_ciks = [c.strip() for c in args.ciks.split(",") if c.strip()]
        if not raw_ciks:
            print(f"{red('ERROR:')} --ciks must be a non-empty comma-separated list")
            return
        parameters["ciks"] = raw_ciks

    # Handle limit parameter
    if args.limit is not None:
        if args.limit <= 0:
            print(f"{red('ERROR:')} Limit must be a positive integer")
            return
        parameters["limit"] = args.limit

    # Handle ticker -> CIK conversion
    if args.ticker and not args.cik:
        # Get repository to convert ticker to CIK
        from backend.app.cli import build_financial_repository
        repo = build_financial_repository()
        if not repo.available():
            print(f"{red('ERROR:')} Financial-DataBase repository not available")
            return

        try:
            company_id = repo._get_company_id_by_ticker(args.ticker.upper())
            if not company_id:
                print(f"{red('ERROR:')} Company with ticker '{args.ticker}' not found")
                return

            # Get CIK from company_identifiers
            conn = repo._get_connection()
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
                    print(f"{red('ERROR:')} No CIK found for ticker '{args.ticker}'")
                    return
                parameters["cik"] = row['identifier_value']
        except Exception as e:
            print(f"{red('ERROR:')} Failed to get CIK for ticker '{args.ticker}': {e}")
            return
    elif args.cik:
        parameters["cik"] = args.cik

    # Debug: print what we're about to execute
    print(f"DEBUG: About to execute script '{script_name}' with parameters: {parameters}", file=sys.stderr)

    # Execute the script
    print_header(f"Executing SQL script: {script_name}")
    result = service.execute_script(script_name, parameters)

    if not result.success:
        print(f"{red('ERROR:')} {result.error_message}")
        return

    # Output results
    if args.output == "json":
        print(json.dumps({
            "script": result.script_name,
            "description": result.description,
            "parameters": result.parameters,
            "rows": result.rows,
            "row_count": result.row_count,
            "execution_time_ms": result.execution_time_ms
        }, indent=2))
    elif args.output == "csv":
        _output_csv(result)
    else:
        _output_table(result)


def _list_scripts(service: SqlAnalysisService):
    """List available SQL scripts."""
    scripts = service.get_available_scripts()

    if not scripts:
        print(f"{yellow('No SQL scripts found in')} {service._scripts_dir}/analysis/")
        return

    print_header("Available SQL Scripts")
    print(f"{'Script Name':<30} {'Description'}")
    print("-" * 80)
    for script in scripts:
        print(f"{script['name']:<30} {script['description']}")


def _output_table(result):
    """Output results as a formatted table."""
    if not result.rows:
        print(f"{yellow('No data returned')}")
        return

    print(f"{green(f'Query executed successfully in {result.execution_time_ms:.2f}ms')}")
    print(f"Rows returned: {result.row_count}")
    print()

    # Get column names from first row
    if result.rows:
        columns = list(result.rows[0].keys())

        # Calculate column widths
        col_widths = {}
        for col in columns:
            col_widths[col] = max(
                len(str(col)),
                max((len(str(row.get(col, ''))) for row in result.rows), default=0)
            )
            # Cap width at 50 characters for readability
            col_widths[col] = min(col_widths[col], 50)

        # Print header
        header = " | ".join(f"{col:<{col_widths[col]}}" for col in columns)
        print(header)
        print("-" * len(header))

        # Print rows
        for row in result.rows:
            row_str = " | ".join(
                f"{str(row.get(col, '')):<{col_widths[col]}}" for col in columns
            )
            print(row_str)


def _output_csv(result):
    """Output results as CSV."""
    if not result.rows:
        print("")
        return

    # Get column names from first row
    columns = list(result.rows[0].keys())

    # Print header
    print(",".join(columns))

    # Print rows
    for row in result.rows:
        values = []
        for col in columns:
            value = row.get(col, '')
            # Quote values that contain commas or quotes
            if isinstance(value, str) and (',' in value or '"' in value or '\n' in value):
                value = f'"{value.replace('"', '""')}"'
            values.append(str(value))
        print(",".join(values))


def cmd_sql_analysis(args):
    """CLI entry point for sql-analysis command."""
    service = SqlAnalysisService()

    if args.list:
        _list_scripts(service)
        return

    if not args.script:
        print("Error: Script name is required")
        return

    # Parse additional parameters
    parameters = {}
    if args.params:
        try:
            parameters = json.loads(args.params)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --params: {e}")
            return

    # Handle limit parameter
    if args.limit is not None:
        if args.limit <= 0:
            print("Error: Limit must be a positive integer")
            return
        parameters["limit"] = args.limit

    # Handle ticker -> CIK conversion
    if args.ticker and not args.cik:
        # Get repository to convert ticker to CIK
        from backend.app.cli import build_financial_repository
        repo = build_financial_repository()
        if not repo.available():
            print("Error: Financial-DataBase repository not available")
            return

        try:
            company_id = repo._get_company_id_by_ticker(args.ticker.upper())
            if not company_id:
                print(f"Error: Company with ticker '{args.ticker}' not found")
                return

            # Get CIK from company_identifiers
            with repo._get_session() as session:
                from sqlalchemy import text
                result = session.execute(
                    text("""
                        SELECT ci.identifier_value
                        FROM company_identifiers ci
                        JOIN data_providers dp ON ci.provider_id = dp.id
                        WHERE ci.company_id = :company_id
                        AND ci.identifier_type = 'CIK'
                        AND dp.name = 'SEC EDGAR'
                    """),
                    {"company_id": company_id}
                )
                row = result.fetchone()
                if not row:
                    print(f"Error: No CIK found for ticker '{args.ticker}'")
                    return
                parameters["cik"] = row[0]
        except Exception as e:
            print(f"Error: Failed to get CIK for ticker '{args.ticker}': {e}")
            return
    elif args.cik:
        parameters["cik"] = args.cik

    # Execute the script
    result = service.execute_script(args.script, parameters)

    if not result.success:
        print(f"Error: {result.error_message}")
        return

    # Output results
    if args.output == "json":
        print(json.dumps({
            "script": result.script_name,
            "description": result.description,
            "parameters": result.parameters,
            "rows": result.rows,
            "row_count": result.row_count,
            "execution_time_ms": result.execution_time_ms
        }, indent=2))
    elif args.output == "csv":
        _output_csv(result)
    else:
        _output_table(result)