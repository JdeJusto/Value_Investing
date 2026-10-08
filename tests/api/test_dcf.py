"""Tests for GET /api/v1/company/{ticker}/dcf (API Phase 2)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_price_service, get_repository
from backend.domain.value_objects.financials_normalized import NormalizedFinancials

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class _Price:
    def get_current_price(self, ticker):
        return 340.0

    def get_market_cap(self, ticker):
        return 3_300_000_000_000.0

    def get_beta(self, ticker):
        return 1.15


class _Repo:
    def __init__(self, rows, name="Apple Inc."):
        self._rows = rows
        self._name = name

    def get_best_available(self, ticker):
        return list(self._rows)

    def get_company_name(self, ticker):
        return self._name if self._rows else None


def _fixture_rows():
    raw = json.loads((FIXTURES / "dcf_aapl_like.json").read_text())
    return [NormalizedFinancials.from_dict(r) for r in raw]


def _empty_rows():
    return [NormalizedFinancials(ticker="AAPL", fiscal_year=2024, period="FY")]


def _client(monkeypatch, repo) -> TestClient:
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_price_service] = lambda: _Price()
    return TestClient(app)


def _get(client, ticker="AAPL", key="test-key"):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get(f"/api/v1/company/{ticker}/dcf", headers=headers)


def test_dcf_returns_a_computable_valuation(monkeypatch):
    client = _client(monkeypatch, _Repo(_fixture_rows()))
    response = _get(client)
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["ticker"] == "AAPL"
    assert data["verdict"] in {"UNDERVALUED", "FAIR", "OVERVALUED"}
    assert data["intrinsic_value"] is not None
    assert data["current_price"] == 340.0
    assert data["margin_of_safety"] is not None
    assert data["variant"] == "standard"
    assert data["assumptions"]["terminal_growth"] == 0.025
    assert isinstance(data["reasons"], list)
    assert body["meta"]["source"] == "mixed"


def test_sensitivity_has_nine_rows(monkeypatch):
    client = _client(monkeypatch, _Repo(_fixture_rows()))
    rows = _get(client).json()["data"]["sensitivity"]
    assert len(rows) == 9
    for row in rows:
        assert set(row) == {"wacc", "growth", "value"}


def test_source_is_always_not_from_canon(monkeypatch):
    for rows in (_fixture_rows(), _empty_rows()):
        client = _client(monkeypatch, _Repo(rows))
        assert _get(client).json()["data"]["source"] == "not-from-canon"


def test_insufficient_data_is_a_200(monkeypatch):
    client = _client(monkeypatch, _Repo(_empty_rows()))
    response = _get(client)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["verdict"] == "INSUFFICIENT_DATA"
    assert data["intrinsic_value"] is None
    assert data["reasons"]
    assert data["sensitivity"] == []


def test_unknown_ticker_404(monkeypatch):
    client = _client(monkeypatch, _Repo([]))
    response = _get(client, ticker="ZZZZ")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKER_NOT_FOUND"


def test_missing_api_key_401(monkeypatch):
    client = _client(monkeypatch, _Repo(_fixture_rows()))
    response = _get(client, key=None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
