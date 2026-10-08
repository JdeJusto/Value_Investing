"""Tests for the REST API skeleton (Phase 1).

Hermetic: no database, no Yahoo, no network. The FastAPI service dependencies
are overridden with stubs and ``API_KEY`` is set per test with monkeypatch.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import backend
from backend.api.app import create_app
from backend.api.deps import get_price_service, get_repository


class _Row:
    """Minimal stand-in for a NormalizedFinancials row."""

    def __init__(self, **kwargs):
        self.sector = kwargs.get("sector", "Technology")
        self.currency = kwargs.get("currency", "USD")
        self.fiscal_year = kwargs.get("fiscal_year", 2025)


class _Repo:
    """Stub repository: rows for any ticker, or none for the 404 case."""

    def __init__(self, rows, name="Apple Inc.", cik="0000320193"):
        self._rows = rows
        self._name = name
        self._cik = cik

    def get_best_available(self, ticker):
        return list(self._rows)

    def get_company_name(self, ticker):
        return self._name if self._rows else None

    def get_cik(self, ticker):
        return self._cik if self._rows else None


class _BoomRepo:
    """Stub repository whose read fails (FDB down)."""

    def get_best_available(self, ticker):
        raise RuntimeError("db down")


class _Price:
    """Stub price service."""

    def get_current_price(self, ticker):
        return 336.67

    def get_market_cap(self, ticker):
        return 4_950_000_000_000.0


class _BoomPrice:
    """Stub price service whose fetches fail (Yahoo down)."""

    def get_current_price(self, ticker):
        raise RuntimeError("yahoo down")

    def get_market_cap(self, ticker):
        raise RuntimeError("yahoo down")


def _client(monkeypatch, *, key="test-key", repo=None, price=None) -> TestClient:
    """Build a TestClient with stubbed services; ``key=None`` unsets API_KEY."""
    if key is None:
        monkeypatch.delenv("API_KEY", raising=False)
    else:
        monkeypatch.setenv("API_KEY", key)
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: (
        repo if repo is not None else _Repo([_Row()])
    )
    app.dependency_overrides[get_price_service] = lambda: (
        price if price is not None else _Price()
    )
    return TestClient(app)


# ---------------------------------------------------------------------------
# system endpoints (no auth)
# ---------------------------------------------------------------------------
def test_health_ok_without_api_key(monkeypatch):
    client = _client(monkeypatch, key=None)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {"status": "ok"}
    assert body["meta"]["source"] == "internal"
    assert body["meta"]["cache_ttl"] == 0
    assert body["meta"]["as_of"].endswith("Z")


def test_version_reports_app_version(monkeypatch):
    client = _client(monkeypatch, key=None)
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["api_version"] == "v1"
    assert data["app_version"] == backend.__version__


# ---------------------------------------------------------------------------
# company endpoint (the real pattern)
# ---------------------------------------------------------------------------
def test_company_returns_envelope(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/api/v1/company/AAPL", headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["ticker"] == "AAPL"
    assert data["name"] == "Apple Inc."
    assert data["sector"] == "Technology"
    assert data["cik"] == "0000320193"
    assert data["price"] == 336.67
    assert data["market_cap"] == 4_950_000_000_000.0
    assert data["currency"] == "USD"
    assert data["fiscal_year"] == 2025
    assert body["meta"]["source"] == "mixed"
    assert body["meta"]["cache_ttl"] == 300


def test_company_lowercase_ticker_is_normalized(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/api/v1/company/aapl", headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    assert response.json()["data"]["ticker"] == "AAPL"


def test_company_unknown_ticker_404(monkeypatch):
    client = _client(monkeypatch, repo=_Repo([]))
    response = client.get("/api/v1/company/ZZZZ", headers={"X-API-Key": "test-key"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKER_NOT_FOUND"


def test_company_price_failure_degrades_to_null(monkeypatch):
    client = _client(monkeypatch, price=_BoomPrice())
    response = client.get("/api/v1/company/AAPL", headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["price"] is None
    assert data["market_cap"] is None


def test_company_repository_failure_503(monkeypatch):
    client = _client(monkeypatch, repo=_BoomRepo())
    response = client.get("/api/v1/company/AAPL", headers={"X-API-Key": "test-key"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# auth (fail closed)
# ---------------------------------------------------------------------------
def test_company_without_api_key_401(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/api/v1/company/AAPL")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_company_wrong_api_key_401(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/api/v1/company/AAPL", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_api_key_unset_503(monkeypatch):
    client = _client(monkeypatch, key=None)
    response = client.get("/api/v1/company/AAPL")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "API_KEY_NOT_CONFIGURED"
