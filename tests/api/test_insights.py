"""Tests for GET /api/v1/company/{ticker}/insights (API Phase 3)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_repository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "financials"


class _Repo:
    """Stub repository: rows drive the 404, facts drive the insights."""

    def __init__(self, rows, facts, name="Apple Inc."):
        self._rows = rows
        self._facts = facts
        self._name = name

    def get_best_available(self, ticker):
        return list(self._rows)

    def get_company_name(self, ticker):
        return self._name if self._rows else None

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


def _get(client, ticker="AAPL", key="test-key"):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get(f"/api/v1/company/{ticker}/insights", headers=headers)


def test_insights_shape_and_order(monkeypatch):
    client = _client(monkeypatch, _Repo([object()], _facts()))
    response = _get(client)
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["ticker"] == "AAPL"
    metrics = data["metrics"]
    assert [metric["metric"] for metric in metrics[:3]] == [
        "revenue",
        "gross_profit",
        "operating_income",
    ]
    assert metrics[-1]["metric"] == "fcf_conversion"
    for metric in metrics:
        assert set(metric) == {
            "metric",
            "label",
            "latest_value",
            "latest_year",
            "yoy_change_pct",
            "cagr_5y",
            "cagr_10y",
            "average_5y",
            "trend",
            "stability",
            "direction_changed",
            "notes",
        }
    assert body["meta"]["source"] == "financial_database"
    assert body["meta"]["cache_ttl"] == 3600


def test_revenue_metric_carries_the_cli_values(monkeypatch):
    client = _client(monkeypatch, _Repo([object()], _facts()))
    data = _get(client).json()["data"]
    revenue = next(
        metric for metric in data["metrics"] if metric["metric"] == "revenue"
    )
    assert revenue["latest_value"] == "$416,161,000,000"
    assert revenue["latest_year"] == 2025
    assert revenue["trend"] == "growing"
    assert revenue["yoy_change_pct"] is not None


def test_metric_without_data_is_null_with_note(monkeypatch):
    client = _client(monkeypatch, _Repo([object()], []))
    response = _get(client)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["warnings"] == ["no facts available for this company"]
    revenue = next(
        metric for metric in data["metrics"] if metric["metric"] == "revenue"
    )
    assert revenue["latest_value"] is None
    assert revenue["average_5y"] is None
    assert revenue["notes"] == ["not reported"]


def test_unknown_ticker_404(monkeypatch):
    client = _client(monkeypatch, _Repo([], []))
    response = _get(client, ticker="ZZZZ")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKER_NOT_FOUND"


def test_missing_api_key_401(monkeypatch):
    client = _client(monkeypatch, _Repo([object()], _facts()))
    response = _get(client, key=None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
