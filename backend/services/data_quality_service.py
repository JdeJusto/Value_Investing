"""Automatic data-quality checks for normalized financial rows.

These are read-only heuristics: they flag values that cannot be true for a
normal operating company (negative revenue, gross profit above revenue, an
unbalanced balance sheet). They never rewrite data; the CLI/report decides
what to do with an issue.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backend.domain.value_objects.financials_normalized import NormalizedFinancials

BALANCE_TOLERANCE = 0.01
GROSS_MARGIN_TOLERANCE = 0.01


@dataclass(frozen=True)
class ValidationIssue:
    ticker: str
    rule: str
    severity: str  # "error" | "warning"
    message: str
    fiscal_year: int | None = None
    value: float | None = None


def validate_rows(
    ticker: str, rows: list[NormalizedFinancials]
) -> list[ValidationIssue]:
    """Return every quality issue found in a company's normalized history."""
    issues: list[ValidationIssue] = []
    current_year = datetime.now(UTC).year
    for row in rows:
        year = row.fiscal_year
        revenue = row.revenue
        if revenue is not None and revenue < 0:
            issues.append(
                ValidationIssue(
                    ticker=ticker,
                    rule="negative_revenue",
                    severity="error",
                    message=f"negative revenue {revenue:,.0f}",
                    fiscal_year=year,
                    value=revenue,
                )
            )
        if revenue == 0:
            issues.append(
                ValidationIssue(
                    ticker=ticker,
                    rule="zero_revenue",
                    severity="warning",
                    message="zero revenue (pre-revenue or missing tag)",
                    fiscal_year=year,
                    value=0.0,
                )
            )
        if (
            revenue is not None
            and revenue > 0
            and row.gross_profit is not None
            and row.gross_profit > revenue * (1 + GROSS_MARGIN_TOLERANCE)
        ):
            issues.append(
                ValidationIssue(
                    ticker=ticker,
                    rule="gross_profit_above_revenue",
                    severity="error",
                    message=(
                        f"gross profit {row.gross_profit:,.0f} > revenue {revenue:,.0f}"
                    ),
                    fiscal_year=year,
                    value=row.gross_profit,
                )
            )
        if (
            row.total_assets not in (None, 0)
            and row.total_liabilities is not None
            and row.stockholders_equity is not None
        ):
            diff = abs(
                row.total_assets - (row.total_liabilities + row.stockholders_equity)
            ) / abs(row.total_assets)
            if diff > BALANCE_TOLERANCE:
                issues.append(
                    ValidationIssue(
                        ticker=ticker,
                        rule="unbalanced_balance_sheet",
                        severity="error",
                        message=(
                            f"assets {row.total_assets:,.0f} != liabilities "
                            f"{row.total_liabilities:,.0f} + equity "
                            f"{row.stockholders_equity:,.0f} ({diff:.1%})"
                        ),
                        fiscal_year=year,
                        value=diff,
                    )
                )
        if year > current_year + 1:
            issues.append(
                ValidationIssue(
                    ticker=ticker,
                    rule="future_fiscal_year",
                    severity="warning",
                    message=f"fiscal year {year} is more than one year ahead",
                    fiscal_year=year,
                )
            )
    return issues


def validate_ticker(ticker: str, repository) -> list[ValidationIssue]:
    """Validate the best available history for one ticker."""
    rows = repository.get_best_available(ticker)
    return validate_rows(ticker, rows)
