"""Hermetic tests for the read-only lookups added for the API.

``get_sector_map`` (screener sector filter) and ``search_companies``
(autocomplete) run against a fake psycopg2-style connection, so no database
is required.
"""

from __future__ import annotations

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)


class _FakeCursor:
    """Dict-row cursor: each ``execute`` asks ``responder`` for rows."""

    def __init__(self, responder):
        self._responder = responder
        self.calls: list[tuple[str, object]] = []
        self._rows: list[dict] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        self._rows = list(self._responder(sql, params) or [])

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConnection:
    def __init__(self, responder):
        self.cursor_obj = _FakeCursor(responder)

    def cursor(self):
        return self.cursor_obj


def _repo(responder) -> tuple[FinancialDatabaseRepository, _FakeConnection]:
    repo = FinancialDatabaseRepository()
    conn = _FakeConnection(responder)
    repo._get_connection = lambda: conn  # type: ignore[method-assign]
    return repo, conn


def test_get_sector_map_returns_ticker_to_sector():
    def responder(sql, params):
        assert "company_listings" in sql
        return [
            {"ticker": "AAPL", "sector": "Technology"},
            {"ticker": "KO", "sector": "Consumer Defensive"},
        ]

    repo, conn = _repo(responder)
    result = repo.get_sector_map(["aapl", "KO", "ZZZZ"])
    assert result == {"AAPL": "Technology", "KO": "Consumer Defensive"}
    assert conn.cursor_obj.calls[0][1] == (["AAPL", "KO", "ZZZZ"],)


def test_get_sector_map_empty_input_skips_the_query():
    repo, conn = _repo(lambda sql, params: [])
    assert repo.get_sector_map([]) == {}
    assert conn.cursor_obj.calls == []


def test_get_sector_map_db_failure_returns_empty():
    def responder(sql, params):
        raise RuntimeError("db down")

    repo, _ = _repo(responder)
    assert repo.get_sector_map(["AAPL"]) == {}


def test_search_companies_skips_name_fallback_when_limit_filled():
    def responder(sql, params):
        if "UPPER(cl.ticker) LIKE" in sql:
            return [{"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"}]
        raise AssertionError("name fallback must not run when the limit is filled")

    repo, conn = _repo(responder)
    result = repo.search_companies("aapl", limit=1)
    assert result == [{"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"}]
    assert len(conn.cursor_obj.calls) == 1


def test_search_companies_falls_back_to_legal_name_and_dedupes():
    def responder(sql, params):
        if "UPPER(cl.ticker) LIKE" in sql:
            return [{"ticker": "APP", "name": "AppLovin Corporation", "sector": "Tech"}]
        assert "UPPER(c.legal_name) LIKE" in sql
        return [
            {"ticker": "APP", "name": "AppLovin Corporation", "sector": "Tech"},
            {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
        ]

    repo, conn = _repo(responder)
    result = repo.search_companies("app", limit=5)
    assert [row["ticker"] for row in result] == ["APP", "AAPL"]
    assert len(conn.cursor_obj.calls) == 2
    # The name query only asks for the remaining slots.
    assert conn.cursor_obj.calls[1][1] == ("%APP%", 4)


def test_search_companies_blank_query_returns_empty():
    repo, conn = _repo(lambda sql, params: [])
    assert repo.search_companies("   ", limit=5) == []
    assert conn.cursor_obj.calls == []


def test_search_companies_db_failure_returns_empty():
    def responder(sql, params):
        raise RuntimeError("db down")

    repo, _ = _repo(responder)
    assert repo.search_companies("app") == []
