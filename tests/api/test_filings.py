"""Tests for the filings endpoints (API Phase 3)."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_repository
from backend.services.financial_statement_parser import (
    Statement,
    StatementLine,
    StatementType,
)
from backend.services.narrative_extractor import NarrativeSection


def _filing_row(
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
        "fiscal_year": None,  # the importer leaves it NULL
        "fiscal_period": "FY",
        "is_amended": is_amended,
        "filing_url": filing_url,
        "cik": cik,
    }


def _effective_year(row):
    anchor = row.get("period_end") or row.get("filing_date")
    return anchor.year if anchor else None


class _Repo:
    """Stub repository: SQL filters emulated in Python for the tests."""

    def __init__(self, rows, name="Apple Inc."):
        self._rows = rows
        self._name = name

    def get_best_available(self, ticker):
        return [object()] if self._rows else []

    def get_company_name(self, ticker):
        return self._name if self._rows else None

    def list_filings(
        self,
        ticker,
        form_types=None,
        fiscal_years=None,
        start_date=None,
        end_date=None,
    ):
        rows = list(self._rows)
        if form_types:
            wanted = {form.upper() for form in form_types}
            rows = [row for row in rows if str(row["form"]).upper() in wanted]
        if fiscal_years:
            wanted_years = {int(year) for year in fiscal_years}
            rows = [row for row in rows if _effective_year(row) in wanted_years]
        return rows

    def get_filing_by_accession(self, accession):
        for row in self._rows:
            if row["accession_number"] == accession:
                found = dict(row)
                found["ticker"] = "AAPL"
                return found
        return None


ROWS = [
    _filing_row(),
    _filing_row(
        accession="0000320193-24-000200",
        form="8-K",
        filing_date="2024-08-01",
        period_end=None,
    ),
]


def _client(monkeypatch, repo) -> TestClient:
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


def _get(client, path, key="test-key"):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get(path, headers=headers)


# ---------------------------------------------------------------------------
# filings list
# ---------------------------------------------------------------------------
def test_filings_list_shape(monkeypatch):
    client = _client(monkeypatch, _Repo(ROWS))
    response = _get(client, "/api/v1/company/AAPL/filings")
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["ticker"] == "AAPL"
    assert data["count"] == 2
    for filing in data["filings"]:
        assert set(filing) == {
            "accession_number",
            "form_type",
            "filing_date",
            "period_of_report",
            "fiscal_year",
            "is_amended",
            "sec_url",
        }
    assert data["available_forms"] == ["10-K", "8-K"]
    assert data["available_years"] == [2024]
    assert body["meta"]["source"] == "financial_database"
    assert body["meta"]["cache_ttl"] == 3600


def test_filings_form_filter(monkeypatch):
    client = _client(monkeypatch, _Repo(ROWS))
    data = _get(client, "/api/v1/company/AAPL/filings?form=10-K").json()["data"]
    assert data["count"] == 1
    assert data["filings"][0]["form_type"] == "10-K"


def test_filings_unknown_ticker_404(monkeypatch):
    client = _client(monkeypatch, _Repo([]))
    response = _get(client, "/api/v1/company/ZZZZ/filings")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKER_NOT_FOUND"


def test_filings_invalid_since_400(monkeypatch):
    client = _client(monkeypatch, _Repo(ROWS))
    response = _get(client, "/api/v1/company/AAPL/filings?since=not-a-date")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DATE"


# ---------------------------------------------------------------------------
# statement
# ---------------------------------------------------------------------------
def _fake_statement():
    return Statement(
        statement_type=StatementType.BALANCE_SHEET,
        lines=[
            StatementLine(
                label="Cash and cash equivalents",
                current="$29,943",
                prior="$29,965",
                indent_level=0,
            ),
            StatementLine(
                label="Total assets",
                current="$364,980",
                prior="$352,583",
                indent_level=0,
            ),
        ],
        source="anchors",
        filing_date=date(2024, 11, 1),
        period_end=date(2024, 9, 28),
        form_type="10-K",
        extraction_warnings=[],
    )


def test_statement_shape(monkeypatch):
    monkeypatch.setattr(
        "backend.api.routes.filings.load_financial_statement",
        lambda record, stype: _fake_statement(),
    )
    client = _client(monkeypatch, _Repo(ROWS))
    response = _get(
        client, "/api/v1/filings/0000320193-24-000123/statement/balance_sheet"
    )
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["accession_number"] == "0000320193-24-000123"
    assert data["form_type"] == "10-K"
    assert data["period_end"] == "2024-09-28"
    assert data["statement_type"] == "balance_sheet"
    assert data["source"] == "anchors"
    assert len(data["lines"]) == 2
    assert data["lines"][0] == {
        "label": "Cash and cash equivalents",
        "current": "$29,943",
        "prior": "$29,965",
        "indent_level": 0,
    }
    assert body["meta"]["source"] == "sec_edgar"
    assert body["meta"]["cache_ttl"] == 86400


def test_statement_unknown_accession_404(monkeypatch):
    client = _client(monkeypatch, _Repo(ROWS))
    response = _get(
        client, "/api/v1/filings/0000000000-00-000000/statement/balance_sheet"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILING_NOT_FOUND"


def test_statement_invalid_type_400(monkeypatch):
    client = _client(monkeypatch, _Repo(ROWS))
    response = _get(client, "/api/v1/filings/0000320193-24-000123/statement/income")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_STATEMENT_TYPE"


def test_statement_not_found_in_filing_is_a_200(monkeypatch):
    monkeypatch.setattr(
        "backend.api.routes.filings.load_financial_statement",
        lambda record, stype: None,
    )
    client = _client(monkeypatch, _Repo(ROWS))
    response = _get(client, "/api/v1/filings/0000320193-24-000123/statement/cash_flow")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["lines"] == []
    assert data["warnings"] == ["Statement not found in filing."]


def test_statement_missing_api_key_401(monkeypatch):
    client = _client(monkeypatch, _Repo(ROWS))
    response = _get(
        client,
        "/api/v1/filings/0000320193-24-000123/statement/balance_sheet",
        key=None,
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# narrative section
# ---------------------------------------------------------------------------
def _fake_section():
    return NarrativeSection(
        section_type="risk_factors",
        filing_date=date(2024, 11, 1),
        period_end=date(2024, 9, 28),
        form_type="10-K",
        title="Item 1A. Risk Factors",
        text=" ".join(f"word{index}" for index in range(150)),
        word_count=150,
        source="toc_anchor",
        extraction_warnings=[],
    )


def test_section_shape(monkeypatch):
    monkeypatch.setattr(
        "backend.api.routes.filings.load_narrative_section",
        lambda record, stype: _fake_section(),
    )
    client = _client(monkeypatch, _Repo(ROWS))
    response = _get(client, "/api/v1/filings/0000320193-24-000123/section/risk_factors")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["accession_number"] == "0000320193-24-000123"
    assert data["form_type"] == "10-K"
    assert data["section_type"] == "risk_factors"
    assert data["title"] == "Item 1A. Risk Factors"
    assert data["word_count"] == 150
    assert data["source"] == "toc_anchor"
    assert data["truncated"] is False
    assert len(data["text"].split()) == 150


def test_section_word_limit_truncates(monkeypatch):
    monkeypatch.setattr(
        "backend.api.routes.filings.load_narrative_section",
        lambda record, stype: _fake_section(),
    )
    client = _client(monkeypatch, _Repo(ROWS))
    data = _get(
        client,
        "/api/v1/filings/0000320193-24-000123/section/risk_factors?word_limit=100",
    ).json()["data"]
    assert data["truncated"] is True
    assert len(data["text"].split()) == 100
    assert data["word_count"] == 150


def test_section_invalid_type_400(monkeypatch):
    client = _client(monkeypatch, _Repo(ROWS))
    response = _get(client, "/api/v1/filings/0000320193-24-000123/section/risk")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SECTION_TYPE"


def test_section_not_found_in_filing_is_a_200(monkeypatch):
    monkeypatch.setattr(
        "backend.api.routes.filings.load_narrative_section",
        lambda record, stype: None,
    )
    client = _client(monkeypatch, _Repo(ROWS))
    response = _get(client, "/api/v1/filings/0000320193-24-000123/section/md_a")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["text"] == ""
    assert data["warnings"] == ["Section not found in filing."]


def test_section_missing_api_key_401(monkeypatch):
    client = _client(monkeypatch, _Repo(ROWS))
    response = _get(
        client,
        "/api/v1/filings/0000320193-24-000123/section/risk_factors",
        key=None,
    )
    assert response.status_code == 401
