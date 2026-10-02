"""FilingService: SEC URL construction, filters, ordering (no live DB)."""

from __future__ import annotations

from datetime import date

from backend.services.filing_service import (
    DEFAULT_FORM_TYPES,
    FilingService,
    build_sec_urls,
)


def _row(
    accession="0000320193-24-000123",
    form="10-K",
    filing_date="2024-11-01",
    period_end="2024-09-28",
    is_amended=False,
    filing_url=None,
    cik="0000320193",
):
    return {
        "accession_number": accession,
        "form": form,
        "filing_date": date.fromisoformat(filing_date),
        "period_end": date.fromisoformat(period_end) if period_end else None,
        "fiscal_year": None,  # the importer leaves it NULL (see the audit)
        "fiscal_period": "FY",
        "is_amended": is_amended,
        "filing_url": filing_url,
        "cik": cik,
    }


class _Repo:
    def __init__(self, rows):
        self._rows = rows
        self.calls: list[dict] = []

    def list_filings(self, ticker, **kwargs):
        self.calls.append({"ticker": ticker, **kwargs})
        return list(self._rows)


def test_index_url_construction_is_exact():
    index_url, document_url = build_sec_urls("0000320193", "0000320193-24-000123")
    assert index_url == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/"
    )
    assert document_url is None  # primary_document does not exist in FDB


def test_document_url_uses_the_stored_filing_url():
    stored = (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/"
        "aapl-20240928.htm"
    )
    index_url, document_url = build_sec_urls(
        "0000320193", "0000320193-24-000123", stored
    )
    assert document_url == stored
    assert index_url.endswith("/000032019324000123/")


def test_urls_are_none_without_a_cik():
    assert build_sec_urls(None, "0000320193-24-000123") == (None, None)
    assert build_sec_urls("", "0000320193-24-000123") == (None, None)


def test_record_exposes_the_index_as_the_best_link():
    service = FilingService(repository=_Repo([_row()]))
    record = service.list_filings("AAPL")[0]
    assert record.sec_url == record.sec_index_url
    assert record.effective_fiscal_year == 2024  # derived from period_end
    assert record.primary_document is None


def test_derived_fiscal_year_falls_back_to_filing_date():
    service = FilingService(repository=_Repo([_row(period_end=None)]))
    record = service.list_filings("AAPL")[0]
    assert record.period_of_report is None
    assert record.effective_fiscal_year == 2024  # filing_date year


def test_filters_are_passed_to_the_repository():
    repo = _Repo([_row()])
    service = FilingService(repository=repo)
    service.list_filings(
        "AAPL",
        form_types=["10-K", "10-Q"],
        fiscal_years=[2024],
        start_date=date(2020, 1, 1),
        end_date=date(2024, 12, 31),
    )
    assert repo.calls[0]["form_types"] == ["10-K", "10-Q"]
    assert repo.calls[0]["fiscal_years"] == [2024]
    assert repo.calls[0]["start_date"] == date(2020, 1, 1)
    assert repo.calls[0]["end_date"] == date(2024, 12, 31)


def test_amendments_can_be_excluded():
    rows = [
        _row(accession="0000320193-24-000200", form="10-K/A", is_amended=True),
        _row(),
    ]
    service = FilingService(repository=_Repo(rows))
    assert len(service.list_filings("AAPL")) == 2
    kept = service.list_filings("AAPL", include_amendments=False)
    assert [record.accession_number for record in kept] == ["0000320193-24-000123"]


def test_ordering_is_filing_date_desc_then_form_asc():
    rows = [
        _row(accession="a", form="10-Q", filing_date="2024-08-02"),
        _row(accession="b", form="8-K", filing_date="2024-08-02"),
        _row(accession="c", form="10-K", filing_date="2024-11-01"),
    ]
    service = FilingService(repository=_Repo(rows))
    records = service.list_filings("AAPL")
    assert [(r.filing_date, r.form_type) for r in records] == [
        (date(2024, 11, 1), "10-K"),
        (date(2024, 8, 2), "10-Q"),
        (date(2024, 8, 2), "8-K"),
    ]


def test_empty_result_for_a_ticker_without_filings():
    service = FilingService(repository=_Repo([]))
    assert service.list_filings("ZZZZ") == []
    assert service.available_form_types("ZZZZ") == []
    assert service.available_fiscal_years("ZZZZ") == []


def test_limit_is_applied_after_ordering():
    rows = [_row(accession=str(i), filing_date=f"2024-0{i}-01") for i in range(1, 6)]
    service = FilingService(repository=_Repo(rows))
    records = service.list_filings("AAPL", limit=2)
    assert len(records) == 2
    assert records[0].filing_date == date(2024, 5, 1)


def test_available_form_types_orders_by_frequency():
    rows = [
        _row(accession="a", form="8-K"),
        _row(accession="b", form="8-K"),
        _row(accession="c", form="10-Q"),
        _row(accession="d", form="10-K"),
    ]
    service = FilingService(repository=_Repo(rows))
    assert service.available_form_types("AAPL") == ["8-K", "10-K", "10-Q"]


def test_available_fiscal_years_are_derived_and_sorted():
    rows = [
        _row(accession="a", period_end="2024-09-28"),
        _row(accession="b", period_end="2023-09-30"),
        _row(accession="c", period_end="2022-09-24"),
    ]
    service = FilingService(repository=_Repo(rows))
    assert service.available_fiscal_years("AAPL") == [2024, 2023, 2022]


def test_default_form_types_cover_the_financial_statements():
    assert DEFAULT_FORM_TYPES == ("10-K", "10-Q", "20-F", "40-F")
