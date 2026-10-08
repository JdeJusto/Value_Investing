"""Filings endpoints — list, statement and narrative sections."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_repository, load_company_rows
from backend.api.responses import ApiError, ok
from backend.services.filing_service import FilingService
from backend.services.financial_statement_parser import (
    StatementType,
    load_financial_statement,
)

router = APIRouter(prefix="/api/v1", tags=["filings"])


@router.get("/company/{ticker}/filings", dependencies=[Depends(require_api_key)])
def company_filings(
    ticker: str,
    form: str | None = None,
    year: int | None = None,
    since: str | None = None,
    include_amendments: bool = True,
    limit: int = 50,
    repository: Any = Depends(get_repository),
) -> dict[str, Any]:
    """Official filings for one company, newest first.

    ``form`` accepts a comma-separated list ("10-K,10-Q"); ``year`` filters on
    the fiscal year derived from the period end; ``since`` is an ISO date.
    """
    normalized = ticker.strip().upper()
    load_company_rows(repository, normalized)

    form_types = (
        [part.strip().upper() for part in form.split(",") if part.strip()]
        if form
        else None
    )
    fiscal_years = [year] if year is not None else None
    start_date = _parse_date(since)

    service = FilingService(repository)
    records = service.list_filings(
        normalized,
        form_types=form_types,
        fiscal_years=fiscal_years,
        start_date=start_date,
        include_amendments=include_amendments,
        limit=limit,
    )
    filings = [_filing_payload(record) for record in records]
    data = {
        "ticker": normalized,
        "filings": filings,
        "count": len(filings),
        "available_forms": service.available_form_types(normalized),
        "available_years": service.available_fiscal_years(normalized),
    }
    return ok(data, source="financial_database", cache_ttl=3600)


@router.get(
    "/filings/{accession}/statement/{statement_type}",
    dependencies=[Depends(require_api_key)],
)
def filing_statement(
    accession: str,
    statement_type: str,
    repository: Any = Depends(get_repository),
) -> dict[str, Any]:
    """One statement from a filing: balance sheet, income or cash flow.

    The parser reads the filing HTML from its cache (fetching once when the
    cache is cold) and caches the parsed lines. A statement the parser cannot
    find returns an empty line list with a warning — never a 500.
    """
    stype = _statement_type(statement_type)
    record = _filing_or_404(repository, accession)
    statement = load_financial_statement(record, stype)
    if statement is None:
        data = {
            "accession_number": record.accession_number,
            "form_type": record.form_type,
            "filing_date": record.filing_date.isoformat(),
            "period_end": _iso(record.period_of_report),
            "statement_type": stype.value,
            "source": "none",
            "warnings": ["Statement not found in filing."],
            "lines": [],
        }
    else:
        data = {
            "accession_number": record.accession_number,
            "form_type": record.form_type,
            "filing_date": record.filing_date.isoformat(),
            "period_end": _iso(statement.period_end or record.period_of_report),
            "statement_type": stype.value,
            "source": statement.source,
            "warnings": list(statement.extraction_warnings),
            "lines": [
                {
                    "label": line.label,
                    "current": line.current,
                    "prior": line.prior,
                    "indent_level": line.indent_level,
                }
                for line in statement.lines
            ],
        }
    return ok(data, source="sec_edgar", cache_ttl=86400)


def _parse_date(value: str | None) -> date | None:
    """ISO date or None; a malformed value is a 400, not a 500."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ApiError(400, "INVALID_DATE", f"Not an ISO date: {value}") from exc


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _statement_type(value: str) -> StatementType:
    try:
        return StatementType((value or "").strip().lower())
    except ValueError as exc:
        raise ApiError(
            400, "INVALID_STATEMENT_TYPE", f"Unknown statement type: {value}"
        ) from exc


def _filing_or_404(repository: Any, accession: str) -> Any:
    """The filing record for an accession, or the standard 404/503 error."""
    try:
        record = FilingService(repository).get_by_accession(accession)
    except Exception as exc:  # a DB failure is a 503, not a 500
        raise ApiError(503, "SERVICE_UNAVAILABLE", "Filing lookup failed") from exc
    if record is None:
        raise ApiError(404, "FILING_NOT_FOUND", f"Unknown filing: {accession}")
    return record


def _filing_payload(record: Any) -> dict[str, Any]:
    """One FilingRecord as JSON-safe primitives."""
    return {
        "accession_number": record.accession_number,
        "form_type": record.form_type,
        "filing_date": record.filing_date.isoformat(),
        "period_of_report": _iso(record.period_of_report),
        "fiscal_year": record.effective_fiscal_year,
        "is_amended": record.is_amended,
        "sec_url": record.sec_url,
    }
