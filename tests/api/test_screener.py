"""Tests for GET /api/v1/screener (API Phase 4).

The expensive pipeline is stubbed through the ``get_screener_source``
dependency; the route's filtering, pagination and caching are exercised on
the fixture rows.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_repository, get_screener_source
from backend.api.routes import screener as screener_routes

# Internal shape returned by the (stubbed) screener source.
ROWS = [
    {
        "ticker": "ADBE",
        "name": "Adobe Inc.",
        "sector": "Technology",
        "price": 230.24,
        "market_cap": 240_000_000_000.0,
        "per": 12.57,
        "roe": 0.6134,
        "fcf_yield": 0.1099,
        "verdict": "BUY",
        "score": 95.68,
        "category": "STALWART",
        "key_reason": "P/E 12.6 < 15",
    },
    {
        "ticker": "KO",
        "name": "The Coca-Cola Company",
        "sector": "Consumer Defensive",
        "price": 62.0,
        "market_cap": 268_000_000_000.0,
        "per": 24.1,
        "roe": 0.42,
        "fcf_yield": 0.032,
        "verdict": "WATCH",
        "score": 61.2,
        "category": "STALWART",
        "key_reason": "Quality above average",
    },
    {
        "ticker": "TINY",
        "name": "Tiny Corp.",
        "sector": "Technology",
        "price": 5.0,
        "market_cap": 400_000_000.0,
        "per": None,
        "roe": 0.05,
        "fcf_yield": None,
        "verdict": "AVOID",
        "score": None,
        "category": "CYCLICAL",
        "key_reason": None,
    },
]


class _Repo:
    """Stub repository (the route never calls it when the source is stubbed)."""


def _client(monkeypatch, rows=None, calls=None) -> TestClient:
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()

    def fake_source(tickers, repository):
        if calls is not None:
            calls.append(list(tickers))
        return [dict(row) for row in (rows if rows is not None else ROWS)]

    app.dependency_overrides[get_repository] = lambda: _Repo()
    app.dependency_overrides[get_screener_source] = lambda: fake_source
    screener_routes._cache.clear()
    screener_routes._compute_locks.clear()
    return TestClient(app)


def _get(client, params=None, key="test-key"):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get("/api/v1/screener", params=params or {}, headers=headers)


def test_screener_shape_and_meta(monkeypatch):
    client = _client(monkeypatch)
    response = _get(client, {"universe": "sp500", "page": 1, "page_size": 50})
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["universe"] == "sp500"
    assert data["methodology"] == "buffett_classic"
    assert data["count"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert data["total_pages"] == 1
    assert data["filters"] == {
        "sector": None,
        "verdict": None,
        "category": None,
        "pe_max": None,
        "roe_min": None,
        "fcf_yield_min": None,
        "market_cap_min": None,
        "market_cap_max": None,
    }
    assert body["meta"]["source"] == "mixed"
    assert body["meta"]["cache_ttl"] == 300
    first = data["rows"][0]
    assert set(first) == {
        "ticker",
        "name",
        "sector",
        "price",
        "market_cap",
        "pe",
        "roe",
        "fcf_yield",
        "verdict",
        "score",
        "category",
        "key_reason",
    }
    assert first["ticker"] == "ADBE"
    assert first["pe"] == 12.57
    assert first["category"] == "STALWART"


def test_pagination_page_two_returns_second_slice(monkeypatch):
    client = _client(monkeypatch)
    response = _get(client, {"page": 2, "page_size": 1})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["count"] == 3
    assert data["total_pages"] == 3
    assert [row["ticker"] for row in data["rows"]] == ["KO"]


def test_page_beyond_the_end_returns_empty_page(monkeypatch):
    client = _client(monkeypatch)
    data = _get(client, {"page": 9, "page_size": 2}).json()["data"]
    assert data["rows"] == []
    assert data["count"] == 3


def test_page_size_is_capped_at_200(monkeypatch):
    client = _client(monkeypatch)
    data = _get(client, {"page_size": 500}).json()["data"]
    assert data["page_size"] == 200


def test_invalid_universe_400(monkeypatch):
    client = _client(monkeypatch)
    response = _get(client, {"universe": "dowjones"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UNIVERSE"


def test_invalid_negative_filter_400(monkeypatch):
    client = _client(monkeypatch)
    response = _get(client, {"pe_max": -1})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILTER"


def test_market_cap_range_inverted_400(monkeypatch):
    client = _client(monkeypatch)
    response = _get(client, {"market_cap_min": 100, "market_cap_max": 10})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILTER"


def test_invalid_verdict_400(monkeypatch):
    client = _client(monkeypatch)
    response = _get(client, {"verdict": "MAYBE"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILTER"


def test_invalid_category_400(monkeypatch):
    client = _client(monkeypatch)
    response = _get(client, {"category": "GROWTH"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILTER"


def test_invalid_page_400(monkeypatch):
    client = _client(monkeypatch)
    response = _get(client, {"page": 0})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PAGE"


def test_sector_filter(monkeypatch):
    client = _client(monkeypatch)
    data = _get(client, {"sector": "Technology"}).json()["data"]
    assert [row["ticker"] for row in data["rows"]] == ["ADBE", "TINY"]
    assert data["count"] == 2


def test_verdict_filter_accepts_comma_separated(monkeypatch):
    client = _client(monkeypatch)
    data = _get(client, {"verdict": "BUY,watch"}).json()["data"]
    assert [row["ticker"] for row in data["rows"]] == ["ADBE", "KO"]


def test_category_filter_normalizes_labels(monkeypatch):
    client = _client(monkeypatch)
    data = _get(client, {"category": "cyclical"}).json()["data"]
    assert [row["ticker"] for row in data["rows"]] == ["TINY"]


def test_numeric_filters_use_percent_and_billions(monkeypatch):
    client = _client(monkeypatch)
    data = _get(
        client,
        {
            "roe_min": 50,  # percent -> 0.50
            "market_cap_min": 200,  # billions -> 2e11
        },
    ).json()["data"]
    assert [row["ticker"] for row in data["rows"]] == ["ADBE"]


def test_numeric_filter_drops_rows_with_missing_metric(monkeypatch):
    client = _client(monkeypatch)
    data = _get(client, {"fcf_yield_min": 1}).json()["data"]
    assert [row["ticker"] for row in data["rows"]] == ["ADBE", "KO"]


def test_cache_serves_second_request_without_recomputing(monkeypatch):
    calls: list = []
    client = _client(monkeypatch, calls=calls)
    assert _get(client, {"universe": "sp500"}).status_code == 200
    assert (
        _get(client, {"universe": "sp500", "sector": "Technology"}).status_code == 200
    )
    assert len(calls) == 1


def test_universe_all_sets_warning(monkeypatch):
    client = _client(monkeypatch)
    data = _get(client, {"universe": "all"}).json()["data"]
    assert "warning" in data
    assert "minutes" in data["warning"]


def test_missing_api_key_401(monkeypatch):
    client = _client(monkeypatch)
    response = _get(client, key=None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
