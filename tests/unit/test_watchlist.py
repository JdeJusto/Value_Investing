"""Unit tests: watchlist models, repository, service and CSV export.

No providers, no network — analytics are mocked.
"""

from datetime import datetime, timezone

import pytest

from backend.watchlist.models import (
    BOUGHT,
    DISCARDED,
    MONITORING,
    Watchlist,
    WatchlistItem,
)
from backend.watchlist.watchlist_repository import JsonWatchlistRepository
from backend.watchlist.watchlist_service import WatchlistService


def _item(ticker, status=MONITORING, note="", year=2026) -> WatchlistItem:
    return WatchlistItem(
        ticker=ticker,
        status=status,
        note=note,
        added_at=datetime(year, 1, 1, tzinfo=timezone.utc),
    )


class MockAnalyzer:
    def __init__(self, result=None, fail=False):
        self._result = result or {
            "ticker": "AAPL",
            "buffett_score": 82.0,
            "moat_analysis": {"moat_type": "STRONG", "moat_score": 80},
            "composite_score": {
                "total_score": 85.0,
                "rating": "A",
                "confidence": "HIGH",
            },
            "dcf_margin_of_safety": 0.25,
            "current_price": 180.0,
            "opportunity": None,
            "delta_metrics": {
                "revenue_growth_delta": 0.03,
                "gross_margin_delta": 0.01,
                "roic_delta": 0.01,
                "fcf_delta": 0.05,
            },
        }
        self._fail = fail
        self.calls = 0

    def __call__(self, ticker):
        self.calls += 1
        if self._fail:
            raise RuntimeError("boom")
        return self._result


@pytest.fixture
def watchlist_repo(tmp_path):
    return JsonWatchlistRepository(tmp_path / "watchlist.json")


@pytest.fixture
def service(watchlist_repo):
    return WatchlistService(watchlist_repo, analyzer=MockAnalyzer())


# ----------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------
def test_item_roundtrip_through_dict():
    item = _item("AAPL", note="entry pendiente")
    restored = WatchlistItem.from_dict(item.to_dict())
    assert restored == item


def test_item_from_dict_normalizes_ticker():
    restored = WatchlistItem.from_dict(
        {"ticker": "aapl", "status": MONITORING, "note": "x"}
    )
    assert restored.ticker == "AAPL"


def test_watchlist_add_inserts_or_replaces():
    watchlist = Watchlist()
    watchlist.add(_item("AAPL", note="a"))
    watchlist.add(_item("AAPL", note="b"))
    assert len(watchlist.items) == 1
    assert watchlist.item("AAPL").note == "b"


def test_watchlist_remove_and_set_status():
    watchlist = Watchlist()
    watchlist.add(_item("AAPL"))
    watchlist.add(_item("KO"))

    assert watchlist.remove("AAPL") is not None
    assert watchlist.item("AAPL") is None

    watchlist.set_status("KO", BOUGHT)
    assert watchlist.item("KO").status == BOUGHT

    with pytest.raises(ValueError):
        watchlist.set_status("KO", "BOGUS")


def test_watchlist_monitoring_filters():
    watchlist = Watchlist()
    watchlist.add(_item("AAPL", MONITORING))
    watchlist.add(_item("KO", DISCARDED))
    assert [i.ticker for i in watchlist.monitoring()] == ["AAPL"]


def test_watchlist_roundtrip_through_dict():
    watchlist = Watchlist()
    watchlist.add(_item("AAPL", note="n"))
    restored = Watchlist.from_dict(watchlist.to_dict())
    assert restored.name == watchlist.name
    assert [i.ticker for i in restored.items] == ["AAPL"]


# ----------------------------------------------------------------------
# Repository
# ----------------------------------------------------------------------
def test_json_repository_roundtrip(watchlist_repo):
    watchlist = Watchlist()
    watchlist.add(_item("AAPL", note="moat fuerte"))
    watchlist_repo.save(watchlist)

    reloaded = watchlist_repo.load()
    assert reloaded.item("AAPL").note == "moat fuerte"


def test_json_repository_missing_file_returns_empty(watchlist_repo):
    assert watchlist_repo.load().items == []


def test_json_repository_corrupt_file_returns_empty(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text("{not json")
    repo = JsonWatchlistRepository(path)
    assert repo.load().items == []


# ----------------------------------------------------------------------
# Service
# ----------------------------------------------------------------------
def test_service_add_remove_status(service):
    service.add("AAPL", note="pendiente")
    service.add("KO")
    assert [i.ticker for i in service.items()] == ["AAPL", "KO"]

    service.set_status("KO", DISCARDED)
    assert service.items()[1].status == DISCARDED

    service.remove("KO")
    assert [i.ticker for i in service.items()] == ["AAPL"]


def test_service_list_view_enriched(service):
    service.add("AAPL")
    view = service.list_view()
    assert len(view) == 1
    row = view[0]
    assert row["buffett_score"] == 82.0
    assert row["moat"] == "STRONG"
    assert row["signal"] in ("BUY", "WATCHLIST", "HOLD")
    assert row["rank"] is not None


def test_service_list_view_without_analyzer(watchlist_repo):
    bare = WatchlistService(watchlist_repo, analyzer=None)
    bare.add("AAPL")
    row = bare.list_view()[0]
    assert row["buffett_score"] is None
    assert row["signal"] is None


def test_service_list_view_analyzer_failure(watchlist_repo):
    service = WatchlistService(watchlist_repo, analyzer=MockAnalyzer(fail=True))
    service.add("AAPL")
    row = service.list_view()[0]
    assert row["buffett_score"] is None
    assert row["signal"] is None


def test_export_rows_include_deltas(service):
    service.add("AAPL")
    rows = service.export_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "AAPL"
    assert row["revenue_growth_delta"] == 0.03
    assert row["rating"] == "A"
    assert row["confidence"] == "HIGH"


def test_export_rows_monitoring_only(service):
    service.add("AAPL", note="monitor")
    service.add("KO")
    service.set_status("KO", BOUGHT)
    rows = service.export_rows(only_monitoring=True)
    assert [r["ticker"] for r in rows] == ["AAPL"]


def test_export_rows_empty(watchlist_repo):
    assert WatchlistService(watchlist_repo).export_rows() == []
