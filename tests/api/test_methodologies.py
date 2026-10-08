"""Tests for GET /api/v1/company/{ticker}/methodologies (API Phase 2)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_price_service, get_repository
from backend.domain.value_objects.financials_normalized import NormalizedFinancials

VERDICTS = {"BUY", "WATCH", "HOLD", "AVOID", "N/A", "INSUFFICIENT_DATA"}


class _Price:
    def get_current_price(self, ticker):
        return 100.0

    def get_market_cap(self, ticker):
        return 1_000_000_000.0


class _Repo:
    def __init__(self, rows, name="Apple Inc."):
        self._rows = rows
        self._name = name

    def get_best_available(self, ticker):
        return list(self._rows)

    def get_company_name(self, ticker):
        return self._name if self._rows else None


def _financial_rows(ticker="AAPL"):
    return [
        NormalizedFinancials(
            ticker=ticker,
            fiscal_year=2024,
            period="FY",
            sector="Financial Services",
            net_income=10e9,
            total_assets=500e9,
            total_liabilities=470e9,
        )
    ]


def _standard_rows(ticker="AAPL"):
    return [
        NormalizedFinancials(
            ticker=ticker,
            fiscal_year=2024,
            period="FY",
            sector="Technology",
            revenue=390e9,
            net_income=97e9,
            operating_cash_flow=118e9,
            capital_expenditure=11e9,
            total_assets=350e9,
            total_liabilities=280e9,
            stockholders_equity=70e9,
            shares_outstanding=15e9,
        )
    ]


def _client(monkeypatch, repo) -> TestClient:
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_price_service] = lambda: _Price()
    return TestClient(app)


def _get(client, ticker="AAPL", key="test-key"):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get(f"/api/v1/company/{ticker}/methodologies", headers=headers)


def test_methodologies_returns_all_eight_with_summary(monkeypatch):
    client = _client(monkeypatch, _Repo(_standard_rows()))
    response = _get(client)
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["ticker"] == "AAPL"
    assert data["name"] == "Apple Inc."
    assert len(data["methodologies"]) == 8
    for entry in data["methodologies"]:
        assert entry["verdict"] in VERDICTS
        assert entry["confidence"] in {"HIGH", "MEDIUM", "LOW"}
        for key in (
            "name",
            "family",
            "score",
            "reasons",
            "red_flags",
            "failed_rules",
            "passed_rules",
        ):
            assert key in entry
    assert body["meta"]["source"] == "mixed"
    assert body["meta"]["cache_ttl"] == 300


def test_summary_counts_match_the_verdicts(monkeypatch):
    client = _client(monkeypatch, _Repo(_standard_rows()))
    data = _get(client).json()["data"]
    verdicts = [entry["verdict"] for entry in data["methodologies"]]
    summary = data["summary"]
    assert summary["buy_count"] == verdicts.count("BUY")
    assert summary["watch_count"] == verdicts.count("WATCH")
    assert summary["hold_count"] == verdicts.count("HOLD")
    assert summary["avoid_count"] == verdicts.count("AVOID")
    assert summary["na_count"] == verdicts.count("N/A")
    assert summary["insufficient_count"] == verdicts.count("INSUFFICIENT_DATA")
    assert summary["consensus_score"] == summary["buy_count"] - summary["avoid_count"]


def test_financial_company_returns_na_with_null_scores(monkeypatch):
    client = _client(monkeypatch, _Repo(_financial_rows()))
    response = _get(client)
    assert response.status_code == 200
    data = response.json()["data"]
    assert all(entry["verdict"] == "N/A" for entry in data["methodologies"])
    assert all(entry["score"] is None for entry in data["methodologies"])
    assert data["summary"]["na_count"] == 8
    # JSON null, never the string "None".
    assert '"score": null' in response.text or '"score":null' in response.text


def test_unknown_ticker_404(monkeypatch):
    client = _client(monkeypatch, _Repo([]))
    response = _get(client, ticker="ZZZZ")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKER_NOT_FOUND"


def test_missing_api_key_401(monkeypatch):
    client = _client(monkeypatch, _Repo(_standard_rows()))
    response = _get(client, key=None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
