"""Tests for GET /api/v1/company/{ticker}/scorecard (API Phase 2).

The endpoint is a thin adapter over the frozen Phase 1 ``ScorecardService``:
these tests pin the envelope, the 404/401 behaviour, and — most importantly —
that ``data`` is the service payload **verbatim** (no reshaping in the API).
No database or Yahoo is touched: both dependencies are overridden with stubs.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_price_service, get_repository
from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.services.scorecard_service import DIMENSION_ORDER, ScorecardService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "financials"


def _row(year: int) -> NormalizedFinancials:
    """One normalized year with the fields the scorecard ratios read."""
    return NormalizedFinancials(
        ticker="AAPL",
        fiscal_year=year,
        revenue=416_161_000_000.0,
        net_income=112_010_000_000.0,
        ebit=123_216_000_000.0,
        interest_expense=3_933_000_000.0,
        total_debt=96_821_000_000.0,
        stockholders_equity=56_950_000_000.0,
        cash_and_equivalents=35_934_000_000.0,
        free_cash_flow=108_807_000_000.0,
        tax_provision=30_000_000_000.0,
        pretax_income=150_000_000_000.0,
        sector="Technology",
        industry="Consumer Electronics",
    )


def _facts() -> list[dict]:
    raw = json.loads((FIXTURES / "aapl_facts.json").read_text())
    return [dict(fact, value=Decimal(str(fact["value"]))) for fact in raw]


class _Repo:
    """Stub repository: rows drive the 404, facts drive the insights."""

    def __init__(self, rows: list[NormalizedFinancials], facts: list[dict]) -> None:
        self._rows = rows
        self._facts = facts

    def get_best_available(self, ticker, max_years: int = 10):
        return list(self._rows)

    def get_company_name(self, ticker):
        return "Apple Inc." if self._rows else None

    def list_all_facts(self, ticker, fiscal_period, max_years):
        return list(self._facts)


class _Prices:
    """Deterministic price stub (in-memory; nothing persisted)."""

    def get_current_price(self, ticker):
        return 240.0

    def get_market_cap(self, ticker):
        return 3_600_000_000_000.0


def _repo(known: bool = True) -> _Repo:
    rows = [_row(year) for year in (2025, 2024, 2023, 2022, 2021)] if known else []
    return _Repo(rows, _facts())


def _client(monkeypatch, repo: _Repo) -> tuple[TestClient, _Prices]:
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()
    prices = _Prices()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_price_service] = lambda: prices
    return TestClient(app), prices


def _get(
    client: TestClient, ticker: str = "AAPL", *, key: str | None = "test-key", **params
):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get(
        f"/api/v1/company/{ticker}/scorecard", headers=headers, params=params
    )


def test_envelope_and_dimension_order(monkeypatch):
    client, _ = _client(monkeypatch, _repo())
    response = _get(client)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["meta"]["source"] == "mixed"
    assert body["meta"]["cache_ttl"] == 3600
    assert body["meta"]["as_of"].endswith("Z")

    data = body["data"]
    assert data["ticker"] == "AAPL"
    assert data["company"] == "Apple Inc."
    assert data["sector"] == "Technology"
    assert data["industry"] == "Consumer Electronics"
    # All six dimensions, in the frozen order.
    assert [dim["key"] for dim in data["dimensions"]] == list(DIMENSION_ORDER)


# ---------------------------------------------------------------------------
# ?format=markdown (the portable report; JSON stays the default)
# ---------------------------------------------------------------------------
def test_json_stays_the_default_content_type(monkeypatch):
    client, _ = _client(monkeypatch, _repo())
    for params in ({}, {"format": "json"}):
        response = _get(client, **params)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert set(response.json()) == {"data", "meta"}


def test_markdown_returns_the_export_as_text_markdown(monkeypatch):
    from backend.services.scorecard_export import scorecard_to_markdown

    repo = _repo()
    client, prices = _client(monkeypatch, repo)
    card = ScorecardService(repo, price_service=prices).build("AAPL", "FY")
    assert card is not None

    response = _get(client, format="markdown")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.text == scorecard_to_markdown(card.to_dict())
    assert response.text.startswith("# AAPL — Apple Inc.\n")


def test_markdown_is_not_wrapped_in_the_envelope(monkeypatch):
    client, _ = _client(monkeypatch, _repo())
    assert not _get(client, format="markdown").text.startswith("{")


def test_unknown_format_is_rejected(monkeypatch):
    client, _ = _client(monkeypatch, _repo())
    response = _get(client, format="pdf")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FORMAT"
    assert "markdown" in response.json()["error"]["message"]


def test_markdown_still_requires_the_api_key(monkeypatch):
    client, _ = _client(monkeypatch, _repo())
    assert _get(client, format="markdown", key=None).status_code == 401


def test_data_is_the_service_payload_verbatim(monkeypatch):
    repo = _repo()
    client, prices = _client(monkeypatch, repo)
    card = ScorecardService(repo, price_service=prices).build("AAPL", "FY")
    assert card is not None
    # JSON round-trip of the service payload (tuples serialize as arrays).
    expected = json.loads(json.dumps(card.to_dict()))

    data = _get(client).json()["data"]
    # No renaming, no added/dropped keys — and key order preserved.
    assert data == expected
    assert list(data) == list(expected)
    assert [list(dim) for dim in data["dimensions"]] == [
        list(dim) for dim in expected["dimensions"]
    ]


def test_ticker_is_normalized(monkeypatch):
    client, _ = _client(monkeypatch, _repo())
    data = _get(client, ticker="aapl").json()["data"]
    assert data["ticker"] == "AAPL"


def test_quarter_period_is_accepted_not_rejected(monkeypatch):
    client, _ = _client(monkeypatch, _repo())
    response = _get(client, period="Q1")
    assert response.status_code == 200
    assert response.json()["data"]["period"] == "Q1"


def test_unknown_ticker_returns_404(monkeypatch):
    client, _ = _client(monkeypatch, _repo(known=False))
    response = _get(client, ticker="ZZZZ")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKER_NOT_FOUND"


def test_missing_api_key_returns_401(monkeypatch):
    client, _ = _client(monkeypatch, _repo())
    response = _get(client, key=None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
