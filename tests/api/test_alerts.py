"""Tests for GET /api/v1/alerts/{ticker} (API Phase 2)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_repository
from backend.services.alert_service import SEVERITY_ORDER

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "financials"


class _Repo:
    """Stub repository: rows drive the 404, facts drive the rules."""

    def __init__(self, rows, facts, name="Edge Co."):
        self._rows = rows
        self._facts = facts
        self._name = name

    def get_best_available(self, ticker):
        return list(self._rows)

    def get_company_name(self, ticker):
        return self._name if self._rows else None

    def list_all_facts(self, ticker, fiscal_period, max_years):
        return list(self._facts)


def _fact_rows():
    raw = json.loads((FIXTURES / "alerts_edge_cases.json").read_text())
    return [dict(fact, value=Decimal(str(fact["value"]))) for fact in raw]


def _client(monkeypatch, repo) -> TestClient:
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


def _get(client, ticker="AAPL", key="test-key"):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get(f"/api/v1/alerts/{ticker}", headers=headers)


def test_alerts_shape_and_summary(monkeypatch):
    repo = _Repo(rows=[object()], facts=_fact_rows())
    client = _client(monkeypatch, repo)
    response = _get(client)
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["ticker"] == "AAPL"
    assert data["rules_evaluated"] == 10
    assert len(data["alerts"]) == 9
    for alert in data["alerts"]:
        assert set(alert) == {
            "rule_id",
            "severity",
            "title",
            "message",
            "evidence",
            "metric_hint",
            "period",
        }
    severities = [alert["severity"] for alert in data["alerts"]]
    summary = data["summary"]
    assert summary["critical"] == severities.count("CRITICAL")
    assert summary["warning"] == severities.count("WARNING")
    assert summary["info"] == severities.count("INFO")
    assert summary["critical"] + summary["warning"] + summary["info"] == len(severities)
    assert body["meta"]["source"] == "mixed"


def test_alerts_sorted_by_severity_then_rule(monkeypatch):
    repo = _Repo(rows=[object()], facts=_fact_rows())
    client = _client(monkeypatch, repo)
    alerts = _get(client).json()["data"]["alerts"]
    keys = [(SEVERITY_ORDER[alert["severity"]], alert["rule_id"]) for alert in alerts]
    assert keys == sorted(keys)


def test_no_alerts_returns_empty_list_and_zero_counts(monkeypatch):
    repo = _Repo(rows=[object()], facts=[])
    client = _client(monkeypatch, repo)
    response = _get(client)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["alerts"] == []
    assert data["summary"] == {"critical": 0, "warning": 0, "info": 0}
    assert data["rules_skipped"] == data["rules_evaluated"]


def test_unknown_ticker_404(monkeypatch):
    repo = _Repo(rows=[], facts=[])
    client = _client(monkeypatch, repo)
    response = _get(client, ticker="ZZZZ")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKER_NOT_FOUND"


def test_missing_api_key_401(monkeypatch):
    repo = _Repo(rows=[object()], facts=_fact_rows())
    client = _client(monkeypatch, repo)
    response = _get(client, key=None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
