"""Automatic quality checks for normalized financial rows."""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.services.data_quality_service import validate_rows, validate_ticker


def _row(**overrides) -> NormalizedFinancials:
    payload = {
        "ticker": "TEST",
        "fiscal_year": 2025,
        "period": "FY",
        "revenue": 100_000_000.0,
        "gross_profit": 40_000_000.0,
        "total_assets": 200_000_000.0,
        "total_liabilities": 120_000_000.0,
        "stockholders_equity": 80_000_000.0,
    }
    payload.update(overrides)
    return NormalizedFinancials.from_dict(payload)


def test_validator_detects_negative_revenue():
    issues = validate_rows("TEST", [_row(revenue=-1_000_000.0)])

    assert any(issue.rule == "negative_revenue" for issue in issues)
    assert issues[0].severity == "error"


def test_validator_detects_unbalanced_balance_sheet():
    issues = validate_rows("TEST", [_row(total_liabilities=90_000_000.0)])

    assert any(issue.rule == "unbalanced_balance_sheet" for issue in issues)


def test_validator_detects_gross_profit_above_revenue():
    issues = validate_rows("TEST", [_row(gross_profit=120_000_000.0)])

    assert any(issue.rule == "gross_profit_above_revenue" for issue in issues)


def test_validator_flags_zero_revenue_as_warning():
    issues = validate_rows("TEST", [_row(revenue=0.0, gross_profit=None)])

    assert any(
        issue.rule == "zero_revenue" and issue.severity == "warning" for issue in issues
    )


def test_validator_flags_a_future_fiscal_year():
    issues = validate_rows("TEST", [_row(fiscal_year=2030)])

    assert any(issue.rule == "future_fiscal_year" for issue in issues)


def test_validator_accepts_a_clean_row():
    assert validate_rows("TEST", [_row()]) == []


def test_validate_ticker_uses_the_best_available_history():
    class _Repo:
        def get_best_available(self, ticker):
            assert ticker == "TEST"
            return [_row(revenue=-5.0)]

    issues = validate_ticker("TEST", _Repo())

    assert any(issue.rule == "negative_revenue" for issue in issues)
