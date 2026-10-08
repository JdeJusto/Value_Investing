"""Tests for the /api/v1/portfolio endpoints (API Phase 5).

Runs against a real ``PortfolioService`` backed by a tmp JSON file, so the
write-lock invariant is exercised end to end; the repository and the price
service are stubs.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import (
    get_portfolio_service,
    get_price_service,
    get_repository,
)
from backend.portfolio.portfolio_repository import JsonPortfolioRepository
from backend.portfolio.portfolio_service import PortfolioService


class _Repo:
    """Stub fundamentals repository: known tickers only."""

    def __init__(self, known=("AAPL", "MSFT")):
        self._known = {ticker.upper() for ticker in known}

    def get_best_available(self, ticker, max_years=None):
        return [object()] if str(ticker).upper() in self._known else []


class _Prices:
    def __init__(self, prices=None):
        self._prices = dict(prices or {})

    def get_current_price(self, ticker):
        return self._prices.get(str(ticker).upper())


def _service(tmp_path) -> PortfolioService:
    return PortfolioService(
        repository=JsonPortfolioRepository(tmp_path / "portfolio.json")
    )


def _client(monkeypatch, service, repo=None, prices=None) -> TestClient:
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()
    app.dependency_overrides[get_portfolio_service] = lambda: service
    app.dependency_overrides[get_repository] = lambda: repo or _Repo()
    app.dependency_overrides[get_price_service] = lambda: prices or _Prices()
    return TestClient(app)


def _headers(key="test-key"):
    return {"X-API-Key": key} if key is not None else {}


def test_get_portfolio_shape_and_summary(monkeypatch, tmp_path):
    service = _service(tmp_path)
    service.add("AAPL", 10.0, 100.0, thesis="moat", signal_at_entry="BUY")
    client = _client(monkeypatch, service)
    response = client.get("/api/v1/portfolio", headers=_headers())
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert len(data["positions"]) == 1
    position = data["positions"][0]
    assert set(position) == {
        "ticker",
        "shares",
        "avg_price",
        "current_price",
        "value",
        "pnl",
        "pnl_pct",
        "thesis",
        "signal",
        "signal_at_entry",
        "price_source",
        "opened_at",
    }
    assert position["ticker"] == "AAPL"
    assert position["shares"] == 10.0
    assert position["avg_price"] == 100.0
    assert position["current_price"] == 100.0
    assert position["value"] == 1000.0
    assert position["pnl"] == 0.0
    assert position["thesis"] == "moat"
    assert position["signal_at_entry"] == "BUY"
    assert position["price_source"] == "stored"
    assert data["summary"] == {
        "cost": 1000.0,
        "value": 1000.0,
        "pnl": 0.0,
        "return_pct": 0.0,
    }
    assert body["meta"]["source"] == "portfolio_json"
    assert body["meta"]["cache_ttl"] == 60


def test_get_portfolio_summary_reflects_saved_prices(monkeypatch, tmp_path):
    service = _service(tmp_path)
    service.add("AAPL", 10.0, 100.0)
    service.save_prices({"AAPL": 120.0})
    client = _client(monkeypatch, service)
    data = client.get("/api/v1/portfolio", headers=_headers()).json()["data"]
    assert data["positions"][0]["value"] == 1200.0
    assert data["positions"][0]["pnl"] == 200.0
    assert data["positions"][0]["pnl_pct"] == 0.2
    assert data["summary"]["pnl"] == 200.0
    assert data["summary"]["return_pct"] == 0.2


def test_empty_portfolio_returns_zero_summary(monkeypatch, tmp_path):
    client = _client(monkeypatch, _service(tmp_path))
    data = client.get("/api/v1/portfolio", headers=_headers()).json()["data"]
    assert data["positions"] == []
    assert data["summary"] == {
        "cost": 0.0,
        "value": 0.0,
        "pnl": 0.0,
        "return_pct": None,
    }


def test_post_creates_position_and_persists(monkeypatch, tmp_path):
    service = _service(tmp_path)
    client = _client(monkeypatch, service)
    response = client.post(
        "/api/v1/portfolio/positions",
        json={
            "ticker": "aapl",
            "shares": 10,
            "price": 180.0,
            "thesis": "moat",
            "signal": "BUY",
        },
        headers=_headers(),
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["ticker"] == "AAPL"
    assert data["shares"] == 10.0
    assert data["avg_price"] == 180.0
    assert data["signal_at_entry"] == "BUY"
    stored = JsonPortfolioRepository(tmp_path / "portfolio.json").load()
    assert stored.position("AAPL").quantity == 10.0


def test_second_post_averages_the_price(monkeypatch, tmp_path):
    service = _service(tmp_path)
    client = _client(monkeypatch, service)
    payload = {"ticker": "AAPL", "shares": 10, "price": 100.0}
    assert (
        client.post(
            "/api/v1/portfolio/positions", json=payload, headers=_headers()
        ).status_code
        == 201
    )
    payload["price"] = 120.0
    assert (
        client.post(
            "/api/v1/portfolio/positions", json=payload, headers=_headers()
        ).status_code
        == 201
    )
    data = client.get("/api/v1/portfolio", headers=_headers()).json()["data"]
    assert data["positions"][0]["shares"] == 20.0
    assert data["positions"][0]["avg_price"] == 110.0


def test_post_with_explicit_date(monkeypatch, tmp_path):
    service = _service(tmp_path)
    client = _client(monkeypatch, service)
    response = client.post(
        "/api/v1/portfolio/positions",
        json={
            "ticker": "AAPL",
            "shares": 1,
            "price": 100.0,
            "date": "2026-10-01",
        },
        headers=_headers(),
    )
    assert response.status_code == 201
    assert response.json()["data"]["opened_at"] == "2026-10-01"


def test_post_invalid_shares_400(monkeypatch, tmp_path):
    client = _client(monkeypatch, _service(tmp_path))
    response = client.post(
        "/api/v1/portfolio/positions",
        json={"ticker": "AAPL", "shares": 0, "price": 100.0},
        headers=_headers(),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_post_invalid_price_400(monkeypatch, tmp_path):
    client = _client(monkeypatch, _service(tmp_path))
    response = client.post(
        "/api/v1/portfolio/positions",
        json={"ticker": "AAPL", "shares": 1, "price": -5},
        headers=_headers(),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_post_future_date_400(monkeypatch, tmp_path):
    client = _client(monkeypatch, _service(tmp_path))
    future = (datetime.now(UTC).date() + timedelta(days=2)).isoformat()
    response = client.post(
        "/api/v1/portfolio/positions",
        json={"ticker": "AAPL", "shares": 1, "price": 100.0, "date": future},
        headers=_headers(),
    )
    assert response.status_code == 400
    assert "future" in response.json()["error"]["message"]


def test_post_malformed_date_400(monkeypatch, tmp_path):
    client = _client(monkeypatch, _service(tmp_path))
    response = client.post(
        "/api/v1/portfolio/positions",
        json={"ticker": "AAPL", "shares": 1, "price": 100.0, "date": "10/01/2026"},
        headers=_headers(),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_post_invalid_signal_400(monkeypatch, tmp_path):
    client = _client(monkeypatch, _service(tmp_path))
    response = client.post(
        "/api/v1/portfolio/positions",
        json={"ticker": "AAPL", "shares": 1, "price": 100.0, "signal": "SELL"},
        headers=_headers(),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_post_unknown_ticker_404(monkeypatch, tmp_path):
    client = _client(monkeypatch, _service(tmp_path))
    response = client.post(
        "/api/v1/portfolio/positions",
        json={"ticker": "ZZZZ", "shares": 1, "price": 100.0},
        headers=_headers(),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKER_NOT_FOUND"


def test_delete_removes_the_position(monkeypatch, tmp_path):
    service = _service(tmp_path)
    service.add("AAPL", 10.0, 100.0)
    client = _client(monkeypatch, service)
    response = client.delete("/api/v1/portfolio/positions/AAPL", headers=_headers())
    assert response.status_code == 200
    assert response.json()["data"] == {"removed": True}
    assert (
        JsonPortfolioRepository(tmp_path / "portfolio.json").load().position("AAPL")
        is None
    )


def test_delete_unknown_position_404(monkeypatch, tmp_path):
    client = _client(monkeypatch, _service(tmp_path))
    response = client.delete("/api/v1/portfolio/positions/AAPL", headers=_headers())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "POSITION_NOT_FOUND"


def test_exit_records_realized_pnl(monkeypatch, tmp_path):
    service = _service(tmp_path)
    service.add("AAPL", 10.0, 100.0)
    client = _client(monkeypatch, service, prices=_Prices({"AAPL": 130.0}))
    response = client.post("/api/v1/portfolio/positions/AAPL/exit", headers=_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ticker"] == "AAPL"
    assert data["exit_price"] == 130.0
    assert data["realized_pnl"] == 300.0
    assert data["realized_pnl_pct"] == 0.3
    stored = JsonPortfolioRepository(tmp_path / "portfolio.json").load()
    assert stored.position("AAPL") is None
    assert stored.positions[0].exit_price == 130.0


def test_exit_unknown_position_404(monkeypatch, tmp_path):
    client = _client(monkeypatch, _service(tmp_path), prices=_Prices({"AAPL": 130.0}))
    response = client.post("/api/v1/portfolio/positions/AAPL/exit", headers=_headers())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "POSITION_NOT_FOUND"


def test_exit_without_a_price_503(monkeypatch, tmp_path):
    service = _service(tmp_path)
    service.add("AAPL", 10.0, 100.0)
    client = _client(monkeypatch, service, prices=_Prices({}))
    response = client.post("/api/v1/portfolio/positions/AAPL/exit", headers=_headers())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_performance_shape(monkeypatch, tmp_path):
    service = _service(tmp_path)
    service.add("AAPL", 10.0, 100.0)
    service.save_prices({"AAPL": 110.0})
    client = _client(monkeypatch, service)
    response = client.get("/api/v1/portfolio/performance", headers=_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["market_value"] == 1100.0
    assert data["cost_basis"] == 1000.0
    assert data["unrealized_pnl"] == 100.0
    assert "allocation" in data
    assert "risk" in data["allocation"]


def test_all_endpoints_require_the_api_key(monkeypatch, tmp_path):
    client = _client(monkeypatch, _service(tmp_path))
    calls = [
        ("GET", "/api/v1/portfolio", None),
        ("GET", "/api/v1/portfolio/performance", None),
        (
            "POST",
            "/api/v1/portfolio/positions",
            {"ticker": "AAPL", "shares": 1, "price": 100.0},
        ),
        ("DELETE", "/api/v1/portfolio/positions/AAPL", None),
        ("POST", "/api/v1/portfolio/positions/AAPL/exit", None),
    ]
    for method, path, payload in calls:
        response = client.request(method, path, json=payload, headers={})
        assert response.status_code == 401, (method, path)
        assert response.json()["error"]["code"] == "UNAUTHORIZED", (method, path)


def test_api_and_cli_writes_do_not_lose_updates(monkeypatch, tmp_path):
    """The API POST and a simulated CLI call (same service) must both land."""
    service = _service(tmp_path)
    original_load = service._load

    def slow_load():
        time.sleep(0.05)  # widen the window an unlocked writer would lose
        return original_load()

    monkeypatch.setattr(service, "_load", slow_load)
    client = _client(monkeypatch, service)
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def api_add() -> None:
        try:
            barrier.wait(timeout=5)
            response = client.post(
                "/api/v1/portfolio/positions",
                json={"ticker": "AAPL", "shares": 1, "price": 100.0},
                headers=_headers(),
            )
            assert response.status_code == 201, response.text
        except Exception as exc:  # noqa: BLE001 — collected, then asserted
            errors.append(exc)

    def cli_add() -> None:
        try:
            barrier.wait(timeout=5)
            service.add("MSFT", 2.0, 50.0)  # the CLI path (same service)
        except Exception as exc:  # noqa: BLE001 — collected, then asserted
            errors.append(exc)

    threads = [threading.Thread(target=api_add), threading.Thread(target=cli_add)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    stored = JsonPortfolioRepository(tmp_path / "portfolio.json").load()
    assert {p.ticker for p in stored.positions} == {"AAPL", "MSFT"}
