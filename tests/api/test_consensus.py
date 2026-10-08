"""Tests for the /api/v1/consensus family (API Phase 4).

Each test writes real consensus JSON files into a tmp directory and points a
``ConsensusService`` at it — the routes never recompute anything.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_consensus_service
from backend.services.consensus_service import ConsensusService

VERDICT_KEYS = [
    "buffett_clark",
    "buffett_classic",
    "fisher_quantitative_subset",
    "graham",
    "graham_dodd",
    "greenblatt",
    "lynch_garp",
    "marks",
]


def _verdicts(buy: int, avoid: int, watch: int = 0, insuff: int = 0, na: int = 0):
    values = ["BUY"] * buy + ["AVOID"] * avoid + ["WATCH"] * watch
    values += ["INSUFFICIENT_DATA"] * insuff + ["N/A"] * na
    remaining = len(VERDICT_KEYS) - len(values)
    assert remaining >= 0, "more verdicts than methodologies"
    values += ["WATCH"] * remaining  # pad so every company has all 8
    return dict(zip(VERDICT_KEYS, values))


def _company(name, category, buy, avoid, score, price=100.0, **kw):
    verdicts = _verdicts(buy, avoid, **kw)
    return {
        "name": name,
        "lynch_category": category,
        "verdicts": verdicts,
        "buy_count": buy,
        "avoid_count": avoid,
        "insufficient_count": kw.get("insuff", 0),
        "na_count": kw.get("na", 0),
        "consensus_score": score,
        "price": price,
        "prices_available": True,
    }


def _payload(date_str: str, universe: str = "sp500") -> dict:
    return {
        "version": 2,
        "date": date_str,
        "universe": universe,
        "prices_available": True,
        "prices_snapshot": {"AAPL": 336.67},
        "companies": {
            "AAPL": _company("Apple Inc.", "Stalwart", 6, 1, 6, 336.67),
            "ADBE": _company("Adobe Inc.", "Fast Grower", 5, 2, 7, 230.24),
            "KO": _company("The Coca-Cola Company", "Slow Grower", 4, 3, 4, 62.0),
            "TINY": _company("Tiny Corp.", "Cyclical", 3, 3, 3, 5.0),
            "BADCO": _company("Bad Co.", "Turnaround", 3, 4, 2, 10.0),
            "JPM": _company("JPMorgan Chase", "Stalwart", 0, 0, 0, 210.0, na=8),
            "HOLE": _company("Data Hole Inc.", "Asset Play", 0, 0, 0, insuff=8),
        },
    }


def _write(directory, date_str: str, **kwargs) -> None:
    (directory / f"consensus_{date_str}.json").write_text(
        json.dumps(_payload(date_str, **kwargs)), encoding="utf-8"
    )


def _client(monkeypatch, directory, svc=None) -> TestClient:
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()
    service = svc or ConsensusService(directory=directory, max_age_days=None)
    app.dependency_overrides[get_consensus_service] = lambda: service
    return TestClient(app)


def _get(client, path, params=None, key="test-key"):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get(path, params=params or {}, headers=headers)


def test_snapshot_shape_and_meta(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    response = _get(client, "/api/v1/consensus")
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["date"] == today
    assert data["universe"] == "sp500"
    assert data["version"] == 2
    assert data["count"] == 7
    assert data["prices_available"] is True
    assert data["na_count"] == 1  # JPM abstains by design
    assert data["buy_distribution"] == {"0": 2, "1": 0, "2": 0, "3": 2, "4+": 3}
    assert data["categories"]["STALWART"] == 2
    assert data["categories"]["FAST_GROWER"] == 1
    assert body["meta"]["source"] == "consensus_json"
    assert body["meta"]["cache_ttl"] == 3600
    assert "warning" not in body["meta"]


def test_missing_file_503(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = _get(client, "/api/v1/consensus")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "CONSENSUS_NOT_AVAILABLE"
    assert "compute_consensus_rankings" in error["message"]


def test_stale_snapshot_serves_200_with_meta_warning(monkeypatch, tmp_path):
    stale = (datetime.now(UTC).date() - timedelta(days=45)).isoformat()
    _write(tmp_path, stale)
    client = _client(monkeypatch, tmp_path)
    body = _get(client, "/api/v1/consensus").json()
    assert body["data"]["date"] == stale
    assert "warning" in body["meta"]
    assert "45 days old" in body["meta"]["warning"]


def test_snapshot_by_date(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    older = (datetime.now(UTC).date() - timedelta(days=2)).isoformat()
    _write(tmp_path, today)
    _write(tmp_path, older, universe="nasdaq100")
    client = _client(monkeypatch, tmp_path)
    data = _get(client, "/api/v1/consensus", {"date": older}).json()["data"]
    assert data["date"] == older
    assert data["universe"] == "nasdaq100"


def test_ranking_default_sorts_by_score(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    data = _get(client, "/api/v1/consensus/ranking", {"top": 3}).json()["data"]
    assert data["by"] == "score"
    # ADBE has the highest stored score (7), then AAPL (6).
    assert [row["ticker"] for row in data["rows"]] == ["ADBE", "AAPL", "KO"]
    first = data["rows"][0]
    assert set(first) >= {"ticker", "name", "category", "consensus_score", "verdicts"}
    assert first["verdict_string"].startswith("BUY/BUY")


def test_ranking_by_buys_uses_the_canonical_order(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    data = _get(client, "/api/v1/consensus/ranking", {"by": "buys", "top": 3}).json()[
        "data"
    ]
    # AAPL has the most BUYs (6) even though ADBE has the higher score.
    assert [row["ticker"] for row in data["rows"]] == ["AAPL", "ADBE", "KO"]


def test_ranking_by_avoids(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    data = _get(client, "/api/v1/consensus/ranking", {"by": "avoids", "top": 2}).json()[
        "data"
    ]
    assert [row["ticker"] for row in data["rows"]] == ["BADCO", "KO"]


def test_ranking_top_is_capped(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    data = _get(client, "/api/v1/consensus/ranking", {"top": 500}).json()["data"]
    assert data["top"] == 100
    assert len(data["rows"]) == 5  # rankable companies only


def test_ranking_excludes_data_holes_and_all_na(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    data = _get(client, "/api/v1/consensus/ranking", {"top": 100}).json()["data"]
    tickers = {row["ticker"] for row in data["rows"]}
    assert "JPM" not in tickers  # all N/A (financial company)
    assert "HOLE" not in tickers  # all INSUFFICIENT_DATA


def test_ranking_invalid_sort_400(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    response = _get(client, "/api/v1/consensus/ranking", {"by": "momentum"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SORT"


def test_by_category_shape(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    data = _get(client, "/api/v1/consensus/by-category", {"per_category": 1}).json()[
        "data"
    ]
    assert data["per_category"] == 1
    categories = data["categories"]
    assert set(categories) == {
        "SLOW_GROWER",
        "STALWART",
        "FAST_GROWER",
        "CYCLICAL",
        "TURNAROUND",
        "ASSET_PLAY",
    }
    assert all(len(rows) <= 1 for rows in categories.values())
    # STALWART has AAPL (rankable) then JPM (excluded); only AAPL shows.
    assert [row["ticker"] for row in categories["STALWART"]] == ["AAPL"]
    assert categories["ASSET_PLAY"] == []  # HOLE is excluded


def test_by_category_per_category_zero_400(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    response = _get(client, "/api/v1/consensus/by-category", {"per_category": 0})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILTER"


def test_disagreement_zone_rows(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    data = _get(client, "/api/v1/consensus/disagreement").json()["data"]
    # KO (4 buys / 3 avoids), TINY (3/3), BADCO (3/4) are inside 3..4 buys
    # with a significant avoid camp; AAPL/ADBE avoid counts are too low.
    assert [row["ticker"] for row in data["rows"]] == ["KO", "TINY", "BADCO"]
    assert data["count"] == 3
    assert all(row["verdict_string"] for row in data["rows"])


def test_disagreement_invalid_range_400(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    response = _get(
        client, "/api/v1/consensus/disagreement", {"min_buy": 5, "max_buy": 2}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILTER"


def test_missing_api_key_401(monkeypatch, tmp_path):
    today = datetime.now(UTC).date().isoformat()
    _write(tmp_path, today)
    client = _client(monkeypatch, tmp_path)
    response = _get(client, "/api/v1/consensus", key=None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
