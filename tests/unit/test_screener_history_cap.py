"""The screener history cap: newest N fiscal years, pushed into SQL."""

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
        # Emulate the SQL cap the repository pushes down.
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


def _fact(year: int, concept: str = "Revenues", value: float = 100.0) -> dict:
    return {
        "concept": concept,
        "value": value,
        "unit": "USD",
        "fiscal_year": year,
        "fiscal_period": "FY",
        "period_end": f"{year}-12-31",
        "period_start": f"{year}-01-01",
    }


def _repo_with_fake_db(monkeypatch, years):
    cursor = _Cursor([_fact(year) for year in years], max(years))
    repo = FinancialDatabaseRepository()
    monkeypatch.setattr(repo, "_get_company_id_by_ticker", lambda ticker: "cid-1")
    monkeypatch.setattr(repo, "_get_company_sector", lambda ticker: None)
    monkeypatch.setattr(repo, "_get_connection", lambda: _Conn(cursor))
    monkeypatch.setattr(repo, "_fetch_split_ratio_facts", lambda company_id: [])
    return repo, cursor


def test_uncapped_read_has_no_sql_cap(monkeypatch):
    repo, cursor = _repo_with_fake_db(monkeypatch, range(2010, 2026))
    rows = repo.list_years("X")
    assert len(rows) == 16
    assert "fiscal_year >= %s" not in cursor.queries[-1]
    assert cursor.params[-1] == ("cid-1",)


def test_capped_read_pushes_the_cap_into_sql(monkeypatch):
    repo, cursor = _repo_with_fake_db(monkeypatch, range(2010, 2026))
    rows = repo.list_years("X", max_years=3)
    assert len(rows) == 3
    assert [row.fiscal_year for row in rows] == [2025, 2024, 2023]
    assert "fiscal_year >= %s" in cursor.queries[-1]
    assert cursor.params[-1] == ("cid-1", 2023)


def test_get_best_available_forwards_max_years(monkeypatch):
    repo, _cursor = _repo_with_fake_db(monkeypatch, range(2010, 2026))
    rows = repo.get_best_available("X", max_years=5)
    assert [row.fiscal_year for row in rows] == [2025, 2024, 2023, 2022, 2021]


def test_capped_read_bypasses_the_instance_cache(monkeypatch):
    repo, _cursor = _repo_with_fake_db(monkeypatch, range(2010, 2026))
    repo.list_years("X", max_years=3)
    assert repo._list_cache_get("X") is None  # never cached


def test_uncapped_read_still_caches(monkeypatch):
    repo, _cursor = _repo_with_fake_db(monkeypatch, range(2010, 2026))
    repo.list_years("X")
    assert repo._list_cache_get("X") is not None


def test_json_repository_accepts_max_years():
    """Regression: the UI loader passes max_years to every repository."""
    from backend.repositories.json_financial_repository import (
        JsonFinancialRepository,
    )

    repository = JsonFinancialRepository("data/demo/fundamentals")
    full = repository.get_best_available("AAPL")
    capped = repository.get_best_available("AAPL", max_years=3)
    assert len(full) == 10
    assert len(capped) == 3
    assert [row.fiscal_year for row in capped] == [2025, 2024, 2023]
