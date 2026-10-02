"""Official SEC filings for a ticker, with EDGAR links (never fetches).

The service reads the ``filings`` table through the repository (SQL-side
filters) and builds the SEC URLs from CIK + accession number. It does **not**
download documents: the UI and the CLI link out to sec.gov.

Reality of the data (see the session audit): ``filings.fiscal_year`` is NULL
for every row and ``fiscal_period`` is always 'FY', so the fiscal year is
derived from ``period_end`` (falling back to ``filing_date``);
``primary_document`` does not exist, so the document URL is only available
when the importer stored ``filing_url`` (0.3% of rows) — otherwise the index
URL is offered.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any

from backend.services.demo_mode import DEMO_ROOT, is_demo

#: What most investors want first; ``--all`` / no filter shows everything.
DEFAULT_FORM_TYPES: tuple[str, ...] = ("10-K", "10-Q", "20-F", "40-F")

_SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
DEMO_FILINGS = DEMO_ROOT / "filings"


def build_sec_urls(
    cik: str | None,
    accession_number: str | None,
    filing_url: str | None = None,
) -> tuple[str | None, str | None]:
    """(index_url, document_url) for one filing.

    The index URL is always derivable from CIK + accession; the document URL
    only exists when the importer stored it (``filing_url``).
    """
    if not cik or not accession_number:
        return None, None
    try:
        cik_no_zeros = str(int(cik))
    except (TypeError, ValueError):
        return None, None
    accession_no_dashes = accession_number.replace("-", "")
    base = f"{_SEC_ARCHIVES}/{cik_no_zeros}/{accession_no_dashes}"
    return base + "/", filing_url or None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@dataclass(frozen=True)
class FilingRecord:
    """One filing with its EDGAR links and derived fields."""

    cik: str
    ticker: str | None
    accession_number: str
    form_type: str
    filing_date: date
    period_of_report: date | None
    fiscal_year: int | None
    fiscal_period: str | None
    primary_document: str | None
    is_amended: bool
    sec_index_url: str | None
    sec_document_url: str | None
    #: Demo fixtures built without a real accession carry this flag; the UI
    #: renders their links as plain text instead of clickable links.
    demo_placeholder: bool = False

    @property
    def sec_url(self) -> str | None:
        """Best available link: the document when known, else the index."""
        return self.sec_document_url or self.sec_index_url

    @property
    def effective_fiscal_year(self) -> int | None:
        """Fiscal year derived from the period (the column is always NULL)."""
        if self.fiscal_year:
            return self.fiscal_year
        source = self.period_of_report or self.filing_date
        return source.year if source else None


class FilingService:
    """List a company's filings with filters; no network, no fetching."""

    def __init__(self, repository: Any = None) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    def _repository(self) -> Any:
        if self._repo is None:
            from backend.app.cli import build_financial_repository

            self._repo = build_financial_repository()
        return self._repo

    @staticmethod
    def _demo_rows(ticker: str) -> list[dict]:
        path = DEMO_FILINGS / f"{ticker}.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return list(data) if isinstance(data, list) else []

    def _to_record(self, ticker: str, row: dict) -> FilingRecord:
        accession = str(row.get("accession_number") or "")
        filing_url = row.get("filing_url") or None
        index_url, document_url = build_sec_urls(
            str(row.get("cik") or ""), accession, filing_url
        )
        return FilingRecord(
            cik=str(row.get("cik") or ""),
            ticker=ticker,
            accession_number=accession,
            form_type=str(row.get("form") or ""),
            filing_date=_as_date(row.get("filing_date")) or date.min,
            period_of_report=_as_date(row.get("period_end")),
            fiscal_year=row.get("fiscal_year"),
            fiscal_period=row.get("fiscal_period"),
            primary_document=(filing_url.rsplit("/", 1)[-1] if filing_url else None),
            is_amended=bool(row.get("is_amended")),
            sec_index_url=index_url,
            sec_document_url=document_url,
            demo_placeholder=bool(row.get("demo_placeholder")),
        )

    # ------------------------------------------------------------------
    def list_filings(
        self,
        ticker: str,
        form_types: list[str] | None = None,
        fiscal_years: list[int] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        include_amendments: bool = True,
        limit: int | None = None,
    ) -> list[FilingRecord]:
        """Filings for a ticker, newest first (filters applied in SQL)."""
        ticker = ticker.upper().strip()
        if is_demo():
            rows = self._demo_rows(ticker)
        else:
            rows = self._repository().list_filings(
                ticker,
                form_types=form_types,
                fiscal_years=fiscal_years,
                start_date=start_date,
                end_date=end_date,
            )

        records = [self._to_record(ticker, row) for row in rows]
        if is_demo():
            # The demo fixtures are small: the same filters, in Python.
            wanted_forms = {form.upper() for form in (form_types or [])}
            if wanted_forms:
                records = [r for r in records if r.form_type in wanted_forms]
            if fiscal_years:
                wanted_years = {int(year) for year in fiscal_years}
                records = [
                    r for r in records if r.effective_fiscal_year in wanted_years
                ]
            if start_date is not None:
                records = [r for r in records if r.filing_date >= start_date]
            if end_date is not None:
                records = [r for r in records if r.filing_date <= end_date]
        if not include_amendments:
            records = [r for r in records if not r.is_amended]
        records.sort(key=lambda r: r.form_type)
        records.sort(key=lambda r: r.filing_date, reverse=True)
        if limit is not None:
            records = records[: int(limit)]
        return records

    def available_form_types(self, ticker: str) -> list[str]:
        """Distinct form types, most frequent first (ties alphabetical)."""
        counts = Counter(record.form_type for record in self.list_filings(ticker))
        return [
            form for form, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    def available_fiscal_years(self, ticker: str) -> list[int]:
        """Distinct effective fiscal years, newest first."""
        years = {
            year
            for record in self.list_filings(ticker)
            if (year := record.effective_fiscal_year) is not None
        }
        return sorted(years, reverse=True)
