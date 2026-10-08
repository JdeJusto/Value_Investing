"""Tests for GET /api/v1/company/{ticker}/financials (API Phase 3)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_repository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "financials"


class _Repo:
    """Stub repository: facts drive the view, rows drive the 404 check."""

    def __init__(self, facts, name="Apple Inc."):
        self._facts = facts
        self._name = name

    def get_best_available(self, ticker):
        return [object()] if self._facts else []

    def get_company_name(self, ticker):
        return self._name if self._facts else None

    def list_all_facts(self, ticker, fiscal_period, max_years):
        return list(self._facts)


def _facts():
    raw = json.loads((FIXTURES / "aapl_facts.json").read_text())
    return [dict(fact, value=Decimal(str(fact["value"]))) for fact in raw]


def _client(monkeypatch, repo) -> TestClient:
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


def _get(client, query="", ticker="AAPL", key="test-key"):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get(f"/api/v1/company/{ticker}/financials{query}", headers=headers)


def _all_rows(data):
    return (
        data["balance_sheet"]
        + data["income_statement"]
        + data["cash_flow"]
        + data["other"]
    )


def test_financials_shape_and_counts(monkeypatch):
    client = _client(monkeypatch, _Repo(_facts()))
    response = _get(client)
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["ticker"] == "AAPL"
    assert data["name"] == "Apple Inc."
    assert data["period"] == "FY"
    assert data["years"] == sorted(data["years"], reverse=True)
    assert data["years"], "the fixture must expose fiscal years"
    counts = data["counts"]
    assert counts["total"] == (
        counts["balance_sheet"]
        + counts["income_statement"]
        + counts["cash_flow"]
        + counts["other"]
    )
    assert counts["total"] == len(_all_rows(data))
    for section in ("balance_sheet", "income_statement", "cash_flow", "other"):
        for row in data[section]:
            assert set(row) == {"concept", "label", "unit", "values"}
            assert set(row["values"]) == {str(year) for year in data["years"]}
    assert body["meta"]["source"] == "financial_database"
    assert body["meta"]["cache_ttl"] == 3600


def test_missing_year_serializes_as_dash(monkeypatch):
    client = _client(monkeypatch, _Repo(_facts()))
    data = _get(client).json()["data"]
    inventory = next(row for row in _all_rows(data) if row["concept"] == "InventoryNet")
    # InventoryNet reports FY2025/FY2024 only; FY2023 must be the dash.
    assert inventory["values"]["2023"] == "—"
    assert inventory["values"]["2025"] == "$5,718,000,000"


def test_abbreviate_returns_compact_strings(monkeypatch):
    client = _client(monkeypatch, _Repo(_facts()))
    plain = _get(client).json()["data"]
    revenue = next(
        row for row in plain["income_statement"] if row["concept"] == "Revenues"
    )
    assert revenue["values"]["2025"] == "$416,161,000,000"

    compact = _get(client, "?abbreviate=true").json()["data"]
    revenue_compact = next(
        row for row in compact["income_statement"] if row["concept"] == "Revenues"
    )
    assert revenue_compact["values"]["2025"] == "$416.16B"


def test_years_limits_the_window(monkeypatch):
    client = _client(monkeypatch, _Repo(_facts()))
    data = _get(client, "?years=2").json()["data"]
    assert len(data["years"]) == 2
    assert data["years"] == sorted(data["years"], reverse=True)


def test_unknown_ticker_404(monkeypatch):
    client = _client(monkeypatch, _Repo([]))
    response = _get(client, ticker="ZZZZ")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKER_NOT_FOUND"


def test_missing_api_key_401(monkeypatch):
    client = _client(monkeypatch, _Repo(_facts()))
    response = _get(client, key=None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
