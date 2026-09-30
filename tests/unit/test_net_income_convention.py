"""Net income convention: the repository labels which concept won.

JPM files both ``NetIncomeLoss`` (consolidated) and
``NetIncomeLossAvailableToCommonStockholdersBasic`` (after preferred
dividends); the priority list picks the latter, so the CLI must say so.
"""

from __future__ import annotations

from datetime import date

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
    _income_convention,
)
from cli.formatters import fmt_net_income


def _fact(concept: str, value: float, year: int = 2025) -> dict:
    return {
        "concept": concept,
        "value": value,
        "unit": "USD",
        "fiscal_year": year,
        "fiscal_period": "FY",
        "period_start": date(year, 1, 1),
        "period_end": date(year, 12, 31),
    }


def _build(*facts):
    repo = FinancialDatabaseRepository()
    statements = repo._normalize_financial_facts(list(facts))
    return repo._build_normalized_financials("TEST", 2025, statements)


def test_available_to_common_wins_and_is_labelled():
    # JPM-style: both tags filed, the common-stockholders figure wins.
    fin = _build(
        _fact("NetIncomeLoss", 57_048.0),
        _fact("NetIncomeLossAvailableToCommonStockholdersBasic", 55_681.0),
    )
    assert fin.net_income == 55_681.0
    assert fin.net_income_convention == "available_to_common"


def test_consolidated_only_is_labelled_consolidated():
    fin = _build(_fact("NetIncomeLoss", 112_010.0))
    assert fin.net_income == 112_010.0
    assert fin.net_income_convention == "consolidated"


def test_no_net_income_leaves_the_convention_empty():
    fin = _build(_fact("Revenues", 1_000.0))
    assert fin.net_income is None
    assert fin.net_income_convention is None


def test_income_convention_helper_mapping():
    assert (
        _income_convention("NetIncomeLossAvailableToCommonStockholdersDiluted")
        == "available_to_common"
    )
    assert _income_convention("ProfitLoss") == "consolidated"
    assert _income_convention("Revenues") is None
    assert _income_convention(None) is None


def test_formatter_appends_the_note_only_for_available_to_common():
    assert "available to common" in fmt_net_income(55_681.0, "available_to_common")
    assert "available to common" not in fmt_net_income(112_010.0, "consolidated")
    assert "USD" in fmt_net_income(112_010.0, "consolidated")
