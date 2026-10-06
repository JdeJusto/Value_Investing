"""Generalized parser: income statement, cash flow, compat and errors."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.financial_statement_parser import (
    STATEMENT_SIGNATURES,
    FinancialStatementParser,
    Statement,
    StatementType,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "filings"


def _parse(name: str, statement_type: StatementType):
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return FinancialStatementParser().parse(html, statement_type)


def test_income_statement_detected_from_the_real_10k():
    statement = _parse("aapl_10k_income_statement.html", StatementType.INCOME_STATEMENT)
    assert statement is not None
    assert statement.statement_type is StatementType.INCOME_STATEMENT
    assert statement.source == "fallback"
    assert statement.extraction_warnings
    labels = [line.label for line in statement.lines]
    assert "Total net sales" in labels
    assert len(statement.lines) >= 20


def test_income_statement_preserves_the_filed_values():
    statement = _parse("aapl_10k_income_statement.html", StatementType.INCOME_STATEMENT)
    assert statement is not None
    # "Products" appears twice (net sales and cost of sales): take the first.
    products = next(line for line in statement.lines if line.label == "Products")
    assert products.current == "$294,866"
    # Filings print the "$" once per block; later rows omit it — and so do we.
    services = next(line for line in statement.lines if line.label == "Services")
    assert services.current == "96,169"
    total = next(line for line in statement.lines if line.label == "Total net sales")
    assert total.current == "391,035"
    assert total.prior == "383,285"


def test_cash_flow_detected_from_the_real_10k():
    statement = _parse("aapl_10k_cash_flow.html", StatementType.CASH_FLOW)
    assert statement is not None
    assert statement.statement_type is StatementType.CASH_FLOW
    labels = [line.label for line in statement.lines]
    assert any("Operating activities" in label for label in labels)
    assert len(statement.lines) >= 25


def test_cash_flow_preserves_the_filed_values():
    statement = _parse("aapl_10k_cash_flow.html", StatementType.CASH_FLOW)
    assert statement is not None
    net_income = next(line for line in statement.lines if line.label == "Net income")
    assert net_income.current == "93,736"  # as filed: no "$" on this row
    assert net_income.prior == "96,995"


def test_wrong_type_does_not_detect_another_statement():
    # The balance-sheet fixture has no "net income + revenue" pair.
    assert _parse("aapl_10k.html", StatementType.CASH_FLOW) is None


def test_unknown_statement_type_raises_a_clear_error():
    with pytest.raises(ValueError, match="unknown statement type"):
        FinancialStatementParser().parse("<html></html>", "income")  # type: ignore[arg-type]


def test_signatures_cover_every_type():
    for statement_type in StatementType:
        signature = STATEMENT_SIGNATURES[statement_type]
        assert signature["anchors"]
        assert signature["required_pairs"]


def test_statement_labels_are_human_readable():
    assert StatementType.BALANCE_SHEET.label == "Balance Sheet"
    assert StatementType.INCOME_STATEMENT.label == "Income Statement"
    assert StatementType.CASH_FLOW.label == "Cash Flow"


def test_backward_compatible_imports_still_work():
    from backend.services.balance_sheet_parser import (  # noqa: F401
        BalanceSheet,
        BalanceSheetLine,
        BalanceSheetParser,
        load_balance_sheet,
    )

    assert BalanceSheet is Statement
    sheet = BalanceSheetParser().parse(
        (FIXTURES / "legacy_10k.html").read_text(encoding="utf-8")
    )
    assert sheet is not None
    assert sheet.statement_type is StatementType.BALANCE_SHEET
    assert callable(load_balance_sheet)


def test_jnj_income_statement_uses_net_earnings_and_sales_to_customers():
    """JNJ labels the bottom line "Net earnings" and the top line "Sales to
    customers"; the signature pairs must recognise both."""
    statement = _parse("jnj_10k_income_statement.html", StatementType.INCOME_STATEMENT)
    assert statement is not None
    labels = [line.label for line in statement.lines]
    assert "Sales to customers" in labels
    assert "Net earnings" in labels
    sales = next(line for line in statement.lines if line.label == "Sales to customers")
    assert sales.current.replace(" ", "") == "$94,193"


def test_income_statement_with_net_loss_income_label_beats_a_bigger_balance_sheet():
    """COLD: the balance sheet matches a required pair by accident and is
    larger; the real income statement says "Statements of Operations" and its
    bottom line is "Net (loss) income", which no pair used to recognise."""
    balance_sheet = (
        "<table>"
        "<tr><td>Condensed Consolidated Balance Sheets</td></tr>"
        "<tr><td>Net earnings</td><td>$10</td></tr>"
        "<tr><td>Revenues</td><td>$100</td></tr>"
        "<tr><td>Total assets</td><td>$500</td></tr>"
        "<tr><td>Total liabilities</td><td>$200</td></tr>"
        "<tr><td>Filler detail that makes this table the biggest one</td></tr>"
        "</table>"
    )
    income_statement = (
        "<table>"
        "<tr><td>Condensed Consolidated Statements of Operations</td></tr>"
        "<tr><td>Revenues:</td><td>$2,601,846</td></tr>"
        "<tr><td>Total costs and expenses</td><td>2,594,612</td></tr>"
        "<tr><td>Net (loss) income</td><td>(115,300)</td></tr>"
        "</table>"
    )
    statement = FinancialStatementParser().parse(
        f"<html><body>{balance_sheet}{income_statement}</body></html>",
        StatementType.INCOME_STATEMENT,
    )
    assert statement is not None
    labels = [line.label for line in statement.lines]
    assert "Net (loss) income" in labels
    assert "Condensed Consolidated Balance Sheets" not in labels


def test_without_a_statement_title_the_largest_matching_table_still_wins():
    """The title preference is a tie-breaker; the historical rule stays."""
    small = (
        "<table><tr><td>Revenues</td><td>$1</td></tr>"
        "<tr><td>Net income</td><td>$1</td></tr></table>"
    )
    big = (
        "<table><tr><td>Revenues</td><td>$2</td></tr>"
        "<tr><td>Net income</td><td>$2</td></tr>"
        "<tr><td>Extra detail</td><td>x</td></tr></table>"
    )
    statement = FinancialStatementParser().parse(
        f"<html><body>{small}{big}</body></html>", StatementType.INCOME_STATEMENT
    )
    assert statement is not None
    assert "Extra detail" in [line.label for line in statement.lines]
