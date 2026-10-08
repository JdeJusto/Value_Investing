"""Tests for GET /api/v1/search (API Phase 4)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_repository

RESULTS = [
    {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
    {"ticker": "APP", "name": "AppLovin Corporation", "sector": "Technology"},
]


class _Repo:
    def __init__(self, results=None, error=None):
        self._results = results if results is not None else RESULTS
        self._error = error
        self.calls: list[tuple[str, int]] = []

    def search_companies(self, query, limit):
        self.calls.append((query, limit))
        if self._error is not None:
            raise self._error
        return list(self._results)


class _NoSearchRepo:
    pass


def _client(monkeypatch, repo) -> TestClient:
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


def _get(client, params=None, key="test-key"):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get("/api/v1/search", params=params or {}, headers=headers)


def test_search_returns_results(monkeypatch):
    repo = _Repo()
    client = _client(monkeypatch, repo)
    response = _get(client, {"q": "app"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {"query": "app", "results": RESULTS, "count": 2}
    assert body["meta"]["source"] == "financial_database"
    assert body["meta"]["cache_ttl"] == 3600
    assert repo.calls == [("app", 20)]


def test_search_clamps_whitespace_and_case_is_preserved_for_the_repo(monkeypatch):
    repo = _Repo()
    client = _client(monkeypatch, repo)
    response = _get(client, {"q": "  aAp  "})
    assert response.status_code == 200
    assert response.json()["data"]["query"] == "aAp"
    assert repo.calls == [("aAp", 20)]


def test_empty_query_400(monkeypatch):
    client = _client(monkeypatch, _Repo())
    response = _get(client, {"q": "   "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_QUERY"


def test_missing_query_400(monkeypatch):
    client = _client(monkeypatch, _Repo())
    response = _get(client)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_QUERY"


def test_no_results_returns_empty_list(monkeypatch):
    client = _client(monkeypatch, _Repo(results=[]))
    response = _get(client, {"q": "zzzz"})
    assert response.status_code == 200
    assert response.json()["data"]["results"] == []
    assert response.json()["data"]["count"] == 0


def test_limit_is_capped_at_50(monkeypatch):
    repo = _Repo()
    client = _client(monkeypatch, repo)
    _get(client, {"q": "app", "limit": 500})
    assert repo.calls == [("app", 50)]


def test_limit_below_one_400(monkeypatch):
    client = _client(monkeypatch, _Repo())
    response = _get(client, {"q": "app", "limit": 0})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILTER"


def test_repository_without_lookup_503(monkeypatch):
    client = _client(monkeypatch, _NoSearchRepo())
    response = _get(client, {"q": "app"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_repository_failure_503(monkeypatch):
    client = _client(monkeypatch, _Repo(error=RuntimeError("db down")))
    response = _get(client, {"q": "app"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_missing_api_key_401(monkeypatch):
    client = _client(monkeypatch, _Repo())
    response = _get(client, {"q": "app"}, key=None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
