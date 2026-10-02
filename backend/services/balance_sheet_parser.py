"""Backward-compatible re-exports of the v0.6.0 balance-sheet parser.

The implementation moved to :mod:`backend.services.financial_statement_parser`
when it was generalized to income statement and cash flow. These aliases keep
every existing import working::

    from backend.services.balance_sheet_parser import BalanceSheet, load_balance_sheet
"""

from __future__ import annotations

from backend.services.financial_statement_parser import (  # noqa: F401
    FinancialStatementParser,
    Statement,
    StatementLine,
    StatementType,
    load_financial_statement,
)

#: v0.6.0 names.
BalanceSheet = Statement
BalanceSheetLine = StatementLine
BalanceSheetParser = FinancialStatementParser
load_balance_sheet = load_financial_statement

__all__ = [
    "BalanceSheet",
    "BalanceSheetLine",
    "BalanceSheetParser",
    "load_balance_sheet",
]
