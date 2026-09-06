"""Financial Database repository implementation for Value Investing.

This repository connects to the Financial-DataBase PostgreSQL database and
implements the FinancialRepository interface by querying the normalized
financial facts and reconstructing NormalizedFinancials objects.
"""

from __future__ import annotations

import os
from typing import Optional, List
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
    ANNUAL_PERIOD,
)
from backend.domain.entities.financials import (
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement,
)


# Concept mapping from Financial-DataBase XBRL concepts to Value Investing fields
# This maps common XBRL concepts to the financial statement fields we use
INCOME_STATEMENT_CONCEPTS = {
    # Revenue
    'Revenues': 'revenue',
    'Revenue': 'revenue',
    'SalesRevenueNet': 'revenue',
    'RevenueFromContractWithCustomerExcludingAssessedTax': 'revenue',

    # Cost of Goods Sold
    'CostOfGoodsSold': 'cogs',
    'CostOfRevenue': 'cogs',

    # Gross Profit
    'GrossProfit': 'gross_profit',

    # Operating Income
    'OperatingIncomeLoss': 'operating_income',
    'OperatingIncome': 'operating_income',

    # EBIT (often same as operating income)
    'OperatingIncomeLoss': 'ebit',

    # EBITDA
    'EBITDA': 'ebitda',

    # Net Income
    'NetIncomeLoss': 'net_income',
    'NetIncome': 'net_income',
    'ProfitLoss': 'net_income',

    # Interest Expense
    'InterestExpense': 'interest_expense',

    # Tax Provision
    'IncomeTaxExpenseBenefit': 'tax_provision',
    'IncomeTaxExpense': 'tax_provision',

    # Pretax Income
    'IncomeLossBeforeIncomeTaxes': 'pretax_income',
    'PretaxIncome': 'pretax_income',
}

BALANCE_SHEET_CONCEPTS = {
    # Total Assets
    'Assets': 'total_assets',
    'AssetsTotal': 'total_assets',

    # Total Liabilities
    'Liabilities': 'total_liabilities',
    'LiabilitiesTotal': 'total_liabilities',

    # Total Debt (approximation)
    'DebtCurrent': 'total_debt',
    'DebtNoncurrent': 'total_debt',
    'LongTermDebt': 'total_debt',
    'LongTermDebtNoncurrent': 'total_debt',

    # Cash and Equivalents
    'CashAndCashEquivalentsAtCarryingValue': 'cash_and_equivalents',
    'CashAndCashEquivalents': 'cash_and_equivalents',

    # Working Capital (calculated as Current Assets - Current Liabilities)
    # We'll calculate this separately since it's not typically stored directly

    # Retained Earnings
    'RetainedEarningsAccumulatedDeficit': 'retained_earnings',
    'RetainedEarnings': 'retained_earnings',

    # Stockholders Equity
    'StockholdersEquity': 'stockholders_equity',
    'TotalEquityGrossMinorityInterest': 'stockholders_equity',
    'ShareholdersEquity': 'stockholders_equity',
}

CASH_FLOW_CONCEPTS = {
    # Operating Cash Flow
    'NetCashProvidedByUsedInOperatingActivities': 'operating_cash_flow',
    'OperatingCashFlow': 'operating_cash_flow',

    # Capital Expenditure (positive value)
    'PaymentsToAcquireProductiveAssets': 'capital_expenditure',
    'CapitalExpenditures': 'capital_expenditure',
    'CapitalExpenditure': 'capital_expenditure',

    # Free Cash Flow (we'll calculate this as Operating CF - CapEx)

    # Depreciation and Amortization
    'DepreciationDepletionAndAmortization': 'depreciation_amortization',
    'DepreciationAndAmortization': 'depreciation_amortization',

    # Dividends Paid
    'PaymentsOfDividends': 'dividends_paid',
    'DividendsPaid': 'dividends_paid',

    # Repurchase of Stock
    'PaymentsForRepurchaseOfEquity': 'repurchase_of_stock',
    'RepurchaseOfCommonStock': 'repurchase_of_stock',

    # Working Capital Change (we'll calculate this)
}


class FinancialDatabaseRepository(FinancialRepository):
    """Repository that reads from Financial-DataBase PostgreSQL database.

    This repository queries the financial_facts table and reconstructs
    NormalizedFinancials objects by mapping XBRL concepts to financial
    statement fields.
    """

    def __init__(self, database_url: Optional[str] = None):
        """Initialize the repository with database connection.

        Args:
            database_url: PostgreSQL connection string. If None, uses
                         FINANCIAL_DATABASE_URL environment variable or
                         default to financial_database instance.
        """
        if database_url is None:
            database_url = os.environ.get(
                "FINANCIAL_DATABASE_URL",
                "postgresql://financial:test@localhost:5432/financial_database"
            )

        self.database_url = database_url
        self._connection = None

    def _get_connection(self):
        """Get or create a database connection."""
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(
                self.database_url,
                cursor_factory=RealDictCursor
            )
        return self._connection

    def close(self):
        """Close the database connection."""
        if self._connection and not self._connection.closed:
            self._connection.close()
            self._connection = None

    def available(self) -> bool:
        """Check if the Financial-DataBase is available."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
        except Exception:
            return False

    def _get_company_id_by_cik(self, cik: str) -> Optional[str]:
        """Get company ID from CIK.

        Args:
            cik: Central Index Key (10-digit string)

        Returns:
            Company UUID if found, None otherwise
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.id
                    FROM companies c
                    JOIN company_identifiers ci ON c.id = ci.company_id
                    JOIN data_providers dp ON ci.provider_id = dp.id
                    WHERE UPPER(ci.identifier_type) = 'CIK'
                      AND UPPER(ci.identifier_value) = %s
                      AND UPPER(dp.name) = 'SEC EDGAR'
                """, (cik.upper(),))
                result = cur.fetchone()
                return str(result['id']) if result else None
        except Exception:
            return None

    def _get_company_id_by_ticker(self, ticker: str) -> Optional[str]:
        """Get company ID from ticker symbol.

        Args:
            ticker: Company ticker symbol (e.g., 'AAPL')

        Returns:
            Company UUID if found, None otherwise
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.id
                    FROM companies c
                    JOIN company_identifiers ci ON c.id = ci.company_id
                    JOIN data_providers dp ON ci.provider_id = dp.id
                    WHERE UPPER(ci.identifier_type) = 'TICKER'
                      AND UPPER(ci.identifier_value) = %s
                      AND UPPER(dp.name) = 'SEC EDGAR'
                """, (ticker.upper(),))
                result = cur.fetchone()
                return str(result['id']) if result else None
        except Exception:
            return None

    def _get_listing_id_by_cik(self, cik: str) -> Optional[str]:
        """Get listing ID for a company's primary listing.

        Args:
            cik: Central Index Key (10-digit string)

        Returns:
            Listing UUID if found, None otherwise
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT cl.id
                    FROM company_listings cl
                    JOIN companies c ON cl.company_id = c.id
                    JOIN company_identifiers ci ON c.id = ci.company_id
                    JOIN data_providers dp ON ci.provider_id = dp.id
                    WHERE UPPER(ci.identifier_type) = 'CIK'
                      AND UPPER(ci.identifier_value) = %s
                      AND UPPER(dp.name) = 'SEC EDGAR'
                      AND cl.is_active = TRUE
                    ORDER BY cl.created_at
                    LIMIT 1
                """, (cik.upper(),))
                result = cur.fetchone()
                return str(result['id']) if result else None
        except Exception:
            return None

    def _normalize_financial_facts(self, facts: List[dict]) -> dict:
        """Normalize a list of financial facts into financial statement components.

        Args:
            facts: List of financial fact dictionaries from database

        Returns:
            Dictionary with financial statement data organized by statement type
        """
        # Initialize statement containers
        income_data = {}
        balance_data = {}
        cash_flow_data = {}

        # Process each fact
        for fact in facts:
            concept = fact['concept']
            value = float(fact['value']) if fact['value'] is not None else None
            unit = fact['unit']
            fiscal_year = fact['fiscal_year']
            fiscal_period = fact['fiscal_period']

            # Skip if no value
            if value is None:
                continue

            # Map to income statement
            if concept in INCOME_STATEMENT_CONCEPTS:
                field_name = INCOME_STATEMENT_CONCEPTS[concept]
                # Handle duplicates by taking the first non-None value
                if field_name not in income_data or income_data[field_name] is None:
                    income_data[field_name] = value

            # Map to balance sheet
            elif concept in BALANCE_SHEET_CONCEPTS:
                field_name = BALANCE_SHEET_CONCEPTS[concept]
                # For total debt, we might want to sum current and non-current
                if field_name == 'total_debt':
                    if field_name not in balance_data:
                        balance_data[field_name] = 0.0
                    if value is not None:
                        balance_data[field_name] += value
                else:
                    # Handle duplicates by taking the first non-None value
                    if field_name not in balance_data or balance_data[field_name] is None:
                        balance_data[field_name] = value

            # Map to cash flow
            elif concept in CASH_FLOW_CONCEPTS:
                field_name = CASH_FLOW_CONCEPTS[concept]
                # Handle capital expenditure (make positive)
                if field_name == 'capital_expenditure' and value is not None:
                    value = abs(value)  # Ensure positive

                # Handle duplicates by taking the first non-None value
                if field_name not in cash_flow_data or cash_flow_data[field_name] is None:
                    cash_flow_data[field_name] = value

        return {
            'income': income_data,
            'balance': balance_data,
            'cash_flow': cash_flow_data
        }

    def _calculate_derived_fields(self, statements: dict) -> dict:
        """Calculate derived fields like working capital and free cash flow.

        Args:
            statements: Dictionary with income, balance, cash_flow data

        Returns:
            Updated statements dictionary with derived fields calculated
        """
        balance = statements['balance']
        cash_flow = statements['cash_flow']

        # Calculate working capital: Current Assets - Current Liabilities
        # Since we don't have current assets/liabilities directly,
        # we'll approximate or skip for now
        # TODO: Add proper current assets/liabilities concept mapping

        # Calculate free cash flow: Operating Cash Flow - Capital Expenditure
        if (cash_flow.get('operating_cash_flow') is not None and
            cash_flow.get('capital_expenditure') is not None):
            cash_flow['free_cash_flow'] = (
                cash_flow['operating_cash_flow'] - cash_flow['capital_expenditure']
            )

        return statements

    def _build_normalized_financials(
        self,
        ticker: str,
        fiscal_year: int,
        statements: dict,
        loaded_at: Optional[datetime] = None
    ) -> NormalizedFinancials:
        """Build a NormalizedFinancials object from statement data.

        Args:
            ticker: Company ticker symbol
            fiscal_year: Fiscal year
            statements: Dictionary with income, balance, cash_flow data
            loaded_at: When this data was loaded (defaults to now)

        Returns:
            NormalizedFinancials object
        """
        if loaded_at is None:
            loaded_at = datetime.now(timezone.utc)

        income = statements['income']
        balance = statements['balance']
        cash_flow = statements['cash_flow']

        # Build IncomeStatement
        income_stmt = None
        if any(v is not None for v in income.values()):
            income_stmt = IncomeStatement(
                revenue=income.get('revenue'),
                cogs=income.get('cogs'),
                gross_profit=income.get('gross_profit'),
                operating_income=income.get('operating_income'),
                ebit=income.get('ebit'),
                ebitda=income.get('ebitda'),
                net_income=income.get('net_income'),
                interest_expense=income.get('interest_expense'),
                tax_provision=income.get('tax_provision'),
                pretax_income=income.get('pretax_income')
            )

        # Build BalanceSheet
        balance_stmt = None
        if any(v is not None for v in balance.values()):
            balance_stmt = BalanceSheet(
                total_assets=balance.get('total_assets'),
                total_liabilities=balance.get('total_liabilities'),
                total_debt=balance.get('total_debt'),
                cash_and_equivalents=balance.get('cash_and_equivalents'),
                working_capital=balance.get('working_capital'),
                retained_earnings=balance.get('retained_earnings'),
                stockholders_equity=balance.get('stockholders_equity')
            )

        # Build CashFlowStatement
        cash_flow_stmt = None
        if any(v is not None for v in cash_flow.values()):
            cash_flow_stmt = CashFlowStatement(
                operating_cash_flow=cash_flow.get('operating_cash_flow'),
                capital_expenditure=cash_flow.get('capital_expenditure'),
                free_cash_flow=cash_flow.get('free_cash_flow'),
                depreciation_amortization=cash_flow.get('depreciation_amortization'),
                dividends_paid=cash_flow.get('dividends_paid'),
                repurchase_of_stock=cash_flow.get('repurchase_of_stock'),
                working_capital_change=cash_flow.get('working_capital_change')
            )

        return NormalizedFinancials(
            ticker=ticker,
            fiscal_year=fiscal_year,
            # Income statement
            revenue=income.get('revenue'),
            cogs=income.get('cogs'),
            gross_profit=income.get('gross_profit'),
            operating_income=income.get('operating_income'),
            ebit=income.get('ebit'),
            ebitda=income.get('ebitda'),
            net_income=income.get('net_income'),
            interest_expense=income.get('interest_expense'),
            tax_provision=income.get('tax_provision'),
            pretax_income=income.get('pretax_income'),
            # Balance sheet
            total_assets=balance.get('total_assets'),
            total_liabilities=balance.get('total_liabilities'),
            total_debt=balance.get('total_debt'),
            cash_and_equivalents=balance.get('cash_and_equivalents'),
            working_capital=balance.get('working_capital'),
            retained_earnings=balance.get('retained_earnings'),
            stockholders_equity=balance.get('stockholders_equity'),
            # Cash flow
            operating_cash_flow=cash_flow.get('operating_cash_flow'),
            capital_expenditure=cash_flow.get('capital_expenditure'),
            free_cash_flow=cash_flow.get('free_cash_flow'),
            depreciation_amortization=cash_flow.get('depreciation_amortization'),
            dividends_paid=cash_flow.get('dividends_paid'),
            repurchase_of_stock=cash_flow.get('repurchase_of_stock'),
            working_capital_change=cash_flow.get('working_capital_change'),
            # Context
            shares_outstanding=None,  # TODO: Get from company_listings or other source
            period=ANNUAL_PERIOD,
            currency='USD',  # TODO: Get from actual unit/currency data
            source=ProviderName.EDGAR,  # Financial-DataBase primarily has SEC data
            loaded_at=loaded_at,
            # Data quality (we don't have this info directly, so use defaults)
            data_completeness=None,
            data_quality_score=None,
            is_complete=False,
            data_source_priority=1,  # SEC EDGAR is high quality
            derived_metrics=[]
        )

    # FinancialRepository interface implementation

    def upsert(self, financials: NormalizedFinancials) -> None:
        """Insert or update a single fiscal-year record.

        Note: This implementation is read-only for Financial-DataBase
        since we're primarily using it as a source of truth.
        For a full bidirectional sync, this would write to the database.
        """
        # For now, we treat Financial-DataBase as read-only
        # In a full implementation, this would write to the database
        # using the same mapping logic in reverse
        pass

    def upsert_many(self, financials: List[NormalizedFinancials]) -> None:
        """Insert or update a batch of fiscal-year records in one operation."""
        # Read-only implementation
        pass

    def get_by_year(
        self, ticker: str, fiscal_year: int
    ) -> Optional[NormalizedFinancials]:
        """Return the normalized record for a given fiscal year, if stored."""
        try:
            # Get company ID from ticker
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return None

            # Get company identifiers to get the CIK for querying financial facts
            conn = self._get_connection()
            with conn.cursor() as cur:
                # Get the CIK for this company
                cur.execute("""
                    SELECT ci.identifier_value as cik
                    FROM company_identifiers ci
                    JOIN data_providers dp ON ci.provider_id = dp.id
                    WHERE ci.company_id = %s
                      AND UPPER(ci.identifier_type) = 'CIK'
                      AND UPPER(dp.name) = 'SEC EDGAR'
                """, (company_id,))

                cik_result = cur.fetchone()
                if not cik_result:
                    return None

                cik = cik_result['cik']

                # Now get financial facts for this company/year
                cur.execute("""
                    SELECT
                        f.concept,
                        f.value,
                        f.unit,
                        f.fiscal_year,
                        f.fiscal_period
                    FROM financial_facts f
                    WHERE f.company_id = %s
                      AND f.fiscal_year = %s
                """, (company_id, fiscal_year))

                facts = cur.fetchall()

                if not facts:
                    return None

                # Normalize the facts
                statements = self._normalize_financial_facts(facts)
                statements = self._calculate_derived_fields(statements)

                # Build and return NormalizedFinancials
                return self._build_normalized_financials(
                    ticker=ticker.upper(),
                    fiscal_year=fiscal_year,
                    statements=statements
                )

        except Exception:
            # In case of any error, return None to let fallback handle it
            return None

    def list_years(self, ticker: str) -> List[NormalizedFinancials]:
        """Return the best record per year for a ticker, most recent first."""
        try:
            # Get company ID from ticker (same as get_by_year)
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return []

            conn = self._get_connection()
            with conn.cursor() as cur:
                # Get the CIK for this company
                cur.execute("""
                    SELECT ci.identifier_value as cik
                    FROM company_identifiers ci
                    JOIN data_providers dp ON ci.provider_id = dp.id
                    WHERE ci.company_id = %s
                      AND UPPER(ci.identifier_type) = 'CIK'
                      AND UPPER(dp.name) = 'SEC EDGAR'
                """, (company_id,))

                cik_result = cur.fetchone()
                if not cik_result:
                    return []

                cik = cik_result['cik']

                # Get all years with data for this company
                cur.execute("""
                    SELECT DISTINCT f.fiscal_year
                    FROM financial_facts f
                    JOIN companies c ON f.company_id = c.id
                    JOIN company_identifiers ci ON c.id = ci.company_id
                    JOIN data_providers dp ON ci.provider_id = dp.id
                    WHERE UPPER(ci.identifier_type) = 'CIK'
                      AND UPPER(ci.identifier_value) = %s
                      AND UPPER(dp.name) = 'SEC EDGAR'
                    ORDER BY f.fiscal_year DESC
                """, (cik,))

                years = [row['fiscal_year'] for row in cur.fetchall()]

                # Get data for each year
                results = []
                for year in years:
                    financials = self.get_by_year(ticker, year)
                    if financials is not None:
                        results.append(financials)

                return results

        except Exception:
            return []

    def list_all(self, ticker: str) -> List[NormalizedFinancials]:
        """Return every stored record (all sources), year desc."""
        # For Financial-DataBase, we primarily have SEC EDGAR data
        # so this is similar to list_years but could include multiple sources
        # if we had them
        return self.list_years(ticker)

    def get_best_available(self, ticker: str) -> List[NormalizedFinancials]:
        """Return the most consistent usable history for a ticker.

        For Financial-DataBase, we assume SEC EDGAR data is consistently
        high quality, so we just return all available years.
        """
        return self.list_years(ticker)

    def has_data(self, ticker: str) -> bool:
        """True if at least one record exists for the ticker."""
        try:
            # Get company ID from ticker
            company_id = self._get_company_id_by_ticker(ticker)
            if not company_id:
                return False

            # Get company identifiers to get the CIK for querying financial facts
            conn = self._get_connection()
            with conn.cursor() as cur:
                # Get the CIK for this company
                cur.execute("""
                    SELECT ci.identifier_value as cik
                    FROM company_identifiers ci
                    WHERE ci.company_id = %s
                      AND ci.identifier_type = 'CIK'
                      AND ci.provider_id = (SELECT id FROM data_providers WHERE name = 'SEC EDGAR')
                """, (company_id,))

                cik_result = cur.fetchone()
                if not cik_result:
                    return False

                cik = cik_result['cik']

                # Check if there's any financial data for this company
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM financial_facts f
                    WHERE f.company_id = %s
                """, (company_id,))

                result = cur.fetchone()
                return result['count'] > 0 if result else False

        except Exception:
            return False

    def delete_ticker(self, ticker: str) -> None:
        """Remove all records for a ticker.

        Read-only implementation - no-op for Financial-DataBase
        since we treat it as a source of truth.
        """
        pass

    def __del__(self):
        """Cleanup connection on object destruction."""
        self.close()