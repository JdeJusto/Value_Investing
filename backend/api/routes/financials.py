"""Financials endpoint — every stored fact, bucketed by statement type."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_repository, load_company_rows
from backend.api.responses import ApiError, ok
from backend.services.financials_view_service import FinancialsViewService

router = APIRouter(prefix="/api/v1/company", tags=["company"])

#: Missing value placeholder for a fiscal year a row does not report.
_MISSING = "—"


@router.get("/{ticker}/financials", dependencies=[Depends(require_api_key)])
def company_financials(
    ticker: str,
    period: str = "FY",
    years: int = 10,
    abbreviate: bool = False,
    repository: Any = Depends(get_repository),
) -> dict[str, Any]:
    """All stored facts for one company, bucketed by statement type.

    ``abbreviate=true`` switches currency rows to the K/M/B/T display
    ("416.16B"); the default keeps the source format
    ("416,161,000,000.00"). Values are strings either way.
    """
    normalized = ticker.strip().upper()
    load_company_rows(repository, normalized)  # 404 when the ticker is unknown

    service = FinancialsViewService(repository)
    view = service.build(
        normalized,
        fiscal_period=period,
        max_years=years,
        abbreviate=abbreviate,
    )
    if view is None:
        raise ApiError(404, "TICKER_NOT_FOUND", f"Unknown ticker: {normalized}")

    return ok(_financials_payload(view), source="financial_database", cache_ttl=3600)


def _financials_payload(view: Any) -> dict[str, Any]:
    """A FinancialsView as JSON-safe primitives (int year keys -> strings)."""
    years = list(view.years)
    balance = [_row_payload(row, years) for row in view.balance_sheet]
    income = [_row_payload(row, years) for row in view.income_statement]
    cash = [_row_payload(row, years) for row in view.cash_flow]
    other = [_row_payload(row, years) for row in view.other]
    return {
        "ticker": view.ticker,
        "name": view.company_name,
        "period": view.fiscal_period,
        "years": years,
        "balance_sheet": balance,
        "income_statement": income,
        "cash_flow": cash,
        "other": other,
        "counts": {
            "balance_sheet": len(balance),
            "income_statement": len(income),
            "cash_flow": len(cash),
            "other": len(other),
            "total": len(balance) + len(income) + len(cash) + len(other),
        },
    }


def _row_payload(row: Any, years: list[int]) -> dict[str, Any]:
    """One FinancialsRow; a year the row does not report serializes as '—'."""
    return {
        "concept": row.concept,
        "label": row.label,
        "unit": row.unit,
        "values": {str(year): row.values.get(year, _MISSING) for year in years},
    }
