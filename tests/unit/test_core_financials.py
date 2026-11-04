"""FDB 0.2.0 reads: core_financials and effective-year merging.

The repository tests use a canned cursor so they stay unit tests (no live
database); the merge tests exercise the deterministic 8-field overlay that
``get_best_available`` applies to every analytical path.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)
from backend.repositories.fdb_mixins.facts_mixin import FactsMixin
from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)


class _Cursor:
    def __init__(self, *, one=None, many=None, error=None):
        self.one = one
        self.many = [] if many is None else many
        self.error = error
        self.sql = ""
        self.params = ()

    def execute(self, sql, params=()):
        self.sql = sql
        self.params = params
        if self.error is not None:
            raise self.error

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _repo(monkeypatch, cursor):
    repo = FinancialDatabaseRepository()
    monkeypatch.setattr(repo, "_get_company_id_by_ticker", lambda ticker: "cid-1")
    monkeypatch.setattr(repo, "_get_connection", lambda: _Conn(cursor))
    return repo


class _MixinRepo(FactsMixin):
    """FactsMixin stand-in: list_all + the FDB 0.2.0 hooks."""

    def __init__(self, rows, cores=None, year=None):
        self.rows = list(rows)
        self.cores = cores or {}
        self.year = year

    def list_all(self, ticker, max_years=None):
        return list(self.rows)

    def get_effective_year(self, ticker):
        return self.year

    def _core_rows_by_year(self, ticker):
        return dict(self.cores)

    _merge_core_row = staticmethod(FinancialDatabaseRepository._merge_core_row)


def _row(
    year: int,
    *,
    revenue: float | None = 100.0,
    net_income: float | None = 10.0,
    assets: float | None = 1_000.0,
    liabilities: float | None = 900.0,
    equity: float | None = 100.0,
) -> NormalizedFinancials:
    return NormalizedFinancials(
        ticker="TEST",
        fiscal_year=year,
        source=ProviderName.EDGAR,
        revenue=revenue,
        net_income=net_income,
        total_assets=assets,
        total_liabilities=liabilities,
        stockholders_equity=equity,
        loaded_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# repository reads
# ---------------------------------------------------------------------------


def test_get_effective_year_uses_the_core_materialized_view(monkeypatch):
    cursor = _Cursor(one={"fiscal_year": 2024})
    repo = _repo(monkeypatch, cursor)

    assert repo.get_effective_year("MRX") == 2024
    assert "core_financials" in cursor.sql
    assert "total_assets IS NOT NULL" in cursor.sql
    assert "stockholders_equity IS NOT NULL" in cursor.sql
    assert cursor.params == ("cid-1", "cid-1")


def test_get_core_financials_returns_the_derived_liability_flag(monkeypatch):
    cursor = _Cursor(
        one={
            "fiscal_year": 2024,
            "period_end": "2024-12-31",
            "revenue": 1_594_700_000,
            "total_assets": 24_312_500_000,
            "stockholders_equity": 976_900_000,
            "liabilities_effective": 23_335_600_000,
            "liabilities_derived": True,
        }
    )
    repo = _repo(monkeypatch, cursor)

    row = repo.get_core_financials("MRX", 2024)

    assert row is not None
    assert row["stockholders_equity"] == 976_900_000
    assert row["liabilities_derived"] is True
    assert "balance_effective" in cursor.sql
    assert cursor.params == ["cid-1", 2024]


def test_get_core_financials_uses_the_effective_year_by_default(monkeypatch):
    cursor = _Cursor(one={"fiscal_year": 2024, "total_assets": 24_312_500_000})
    repo = _repo(monkeypatch, cursor)
    monkeypatch.setattr(repo, "get_effective_year", lambda ticker: 2024)

    row = repo.get_core_financials("MRX")

    assert row is not None and row["fiscal_year"] == 2024
    assert cursor.params == ["cid-1", 2024]


def test_get_core_financials_batch_resolves_effective_years_in_sql(monkeypatch):
    cursor = _Cursor(
        many=[
            {"ticker": "AAPL", "fiscal_year": 2025, "revenue": 416_161_000_000},
            {"ticker": "MRX", "fiscal_year": 2024, "revenue": 1_594_700_000},
        ]
    )
    repo = _repo(monkeypatch, cursor)

    rows = repo.get_core_financials_batch(["AAPL", "MRX"])

    assert set(rows) == {"AAPL", "MRX"}
    assert "WITH selected" in cursor.sql
    assert "stockholders_equity IS NOT NULL" in cursor.sql
    assert cursor.params == (["AAPL", "MRX"],)


def test_get_core_financials_batch_returns_rows_by_ticker(monkeypatch):
    cursor = _Cursor(
        many=[
            {"ticker": "AAPL", "fiscal_year": 2025, "revenue": 416_161_000_000},
            {"ticker": "MRX", "fiscal_year": 2025, "revenue": 2_024_100_000},
        ]
    )
    repo = _repo(monkeypatch, cursor)

    rows = repo.get_core_financials_batch(["AAPL", "MRX"], fiscal_year=2025)

    assert set(rows) == {"AAPL", "MRX"}
    assert rows["AAPL"]["revenue"] == 416_161_000_000
    assert "ticker = ANY(%s)" in cursor.sql


def test_get_normalized_facts_exposes_field_and_concept(monkeypatch):
    cursor = _Cursor(
        many=[
            {
                "fiscal_year": 2024,
                "field": "total_assets",
                "normalized_concept": "Assets",
                "concept": "Assets",
                "value": 24_312_500_000,
                "unit": "USD",
                "period_end": "2024-12-31",
            }
        ]
    )
    repo = _repo(monkeypatch, cursor)

    rows = repo.get_normalized_facts("MRX")

    assert rows[0]["field"] == "total_assets"
    assert rows[0]["normalized_concept"] == "Assets"
    assert "financial_facts_normalized" in cursor.sql
    assert cursor.params == ("cid-1", "FY")


def test_get_balance_effective_returns_the_latest_period(monkeypatch):
    cursor = _Cursor(
        one={
            "fiscal_year": 2024,
            "period_end": "2024-12-31",
            "liabilities_effective": 23_335_600_000,
            "liabilities_derived": True,
        }
    )
    repo = _repo(monkeypatch, cursor)

    row = repo.get_balance_effective("MRX", 2024)

    assert row is not None and row["liabilities_derived"] is True
    assert "balance_effective" in cursor.sql
    assert cursor.params == ("cid-1", 2024)


# ---------------------------------------------------------------------------
# analytical-path merge
# ---------------------------------------------------------------------------


def test_get_best_available_drops_years_newer_than_the_effective_year():
    repo = _MixinRepo(
        rows=[
            _row(2025, revenue=2_024_100_000, equity=None),
            _row(2024, revenue=1_594_700_000),
        ],
        year=2024,
    )

    rows = repo.get_best_available("MRX")

    assert [row.fiscal_year for row in rows] == [2024]


def test_get_best_available_merges_the_eight_core_fields():
    repo = _MixinRepo(
        rows=[_row(2024, revenue=1_594_700_000, liabilities=23_335_600_000)],
        cores={
            2024: {
                "revenue": 1_600_000_000,
                "net_income": 218_000_000,
                "total_assets": 24_312_500_000,
                "total_liabilities": None,
                "stockholders_equity": 976_900_000,
                "cash": 3_000_000_000,
            }
        },
        year=2024,
    )

    row = repo.get_best_available("MRX")[0]

    assert row.revenue == 1_600_000_000
    assert row.net_income == 218_000_000
    assert row.stockholders_equity == 976_900_000
    assert row.cash_and_equivalents == 3_000_000_000
    # Liabilities is derived from Assets - Equity when the MV has no value.
    assert row.total_liabilities == 24_312_500_000 - 976_900_000


def test_get_best_available_keeps_all_years_when_no_effective_year():
    repo = _MixinRepo(
        rows=[_row(2025, equity=None), _row(2024)],
        cores={2025: {"revenue": 111.0}},
        year=None,
    )

    rows = repo.get_best_available("TEST")

    assert [row.fiscal_year for row in rows] == [2025, 2024]
    assert rows[0].revenue == 111.0


def test_get_best_available_still_drops_all_empty_buckets():
    repo = _MixinRepo(
        rows=[
            _row(
                2025,
                revenue=None,
                net_income=None,
                assets=None,
                liabilities=None,
                equity=None,
            ),
            _row(2024),
        ],
        year=2024,
    )

    rows = repo.get_best_available("TEST")

    assert [row.fiscal_year for row in rows] == [2024]
