"""FinancialDatabaseRepository.list_all_facts: SQL shape and degradation."""

from __future__ import annotations

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)


class _Cursor:
    """Fake psycopg cursor: records SQL, returns canned dict rows."""

    def __init__(self, rows, latest_year):
        self._rows = rows
        self._latest_year = latest_year
        self.queries: list[str] = []
        self.params: list[tuple] = []
        self._result: list | dict | None = None

    def execute(self, sql, params=()):
        self.queries.append(sql)
        self.params.append(params)
        if "MAX(fiscal_year)" in sql:
            self._result = {"max": self._latest_year}
            return
        if "fiscal_year >= %s" in sql:
            min_year = params[-1]
            self._result = [row for row in self._rows if row["fiscal_year"] >= min_year]
        else:
            self._result = self._rows

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _fact(year: int, concept: str = "Revenues") -> dict:
    return {
        "concept": concept,
        "fiscal_year": year,
        "fiscal_period": "FY",
        "value": 100.0,
        "unit": "USD",
        "period_end": f"{year}-12-31",
        "namespace": "us-gaap",
        "frame": None,
    }


def _repo_with_fake_db(monkeypatch, years, ticker_known=True):
    cursor = _Cursor([_fact(year) for year in years], max(years))
    repo = FinancialDatabaseRepository()
    monkeypatch.setattr(
        repo,
        "_get_company_id_by_ticker",
        lambda ticker: "cid-1" if ticker_known else None,
    )
    monkeypatch.setattr(repo, "_get_connection", lambda: _Conn(cursor))
    return repo, cursor


def test_returns_flat_fact_rows(monkeypatch):
    repo, cursor = _repo_with_fake_db(monkeypatch, range(2023, 2026))
    rows = repo.list_all_facts("AAPL", "FY")
    assert len(rows) == 3
    assert rows[0]["concept"] == "Revenues"
    assert rows[0]["namespace"] == "us-gaap"
    assert "ORDER BY f.concept ASC" in cursor.queries[-1]
    assert "UPPER(f.fiscal_period) = %s" in cursor.queries[-1]
    assert cursor.params[-1] == ("cid-1", "FY")


def test_cap_pushes_the_min_year_into_sql(monkeypatch):
    repo, cursor = _repo_with_fake_db(monkeypatch, range(2010, 2026))
    rows = repo.list_all_facts("AAPL", "FY", max_years=5)
    assert len(rows) == 5
    assert all(row["fiscal_year"] >= 2021 for row in rows)
    assert "fiscal_year >= %s" in cursor.queries[-1]
    assert cursor.params[-1] == ("cid-1", "FY", 2021)


def test_unknown_ticker_returns_empty(monkeypatch):
    repo, _ = _repo_with_fake_db(monkeypatch, range(2023, 2026), ticker_known=False)
    assert repo.list_all_facts("ZZZZ") == []


def test_broken_connection_degrades_to_empty(monkeypatch):
    repo = FinancialDatabaseRepository()
    monkeypatch.setattr(repo, "_get_company_id_by_ticker", lambda ticker: "cid-1")

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(repo, "_get_connection", _boom)
    assert repo.list_all_facts("AAPL") == []
