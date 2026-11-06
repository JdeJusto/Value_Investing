"""10-year core_financials timeseries (hermetic)."""

from __future__ import annotations

from backend.repositories.financial_database_repository import (
    FIELDS_OF_INTEREST,
    FinancialDatabaseRepository,
)


class _Cursor:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, *_args, **_kwargs):
        return None

    def fetchall(self):
        return list(self._rows)


class _Connection:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def cursor(self):
        return _Cursor(self._rows)


class _Repo(FinancialDatabaseRepository):
    def __init__(self, rows: list[dict]) -> None:
        super().__init__()
        self._rows = rows

    def _get_company_id_by_ticker(self, _ticker: str) -> str:
        return "company-id"

    def _get_connection(self):
        return _Connection(self._rows)


def _row(year: int, period_end: str, **values) -> dict:
    data = {"fiscal_year": year, "period_end": period_end}
    data.update({field: None for field in FIELDS_OF_INTEREST})
    data.update(values)
    return data


def test_timeseries_aapl_10_years():
    rows = [
        _row(year, f"{year}-09-30", revenue=float(year)) for year in range(2016, 2026)
    ]
    series = _Repo(rows).get_financial_timeseries("AAPL", years=10)

    assert list(series) == list(FIELDS_OF_INTEREST)
    assert len(series["revenue"]) == 10
    assert series["revenue"][0] == (2016, 2016.0)
    assert series["revenue"][-1] == (2025, 2025.0)
    assert series["net_income"][0] == (2016, None)


def test_timeseries_dedup_by_fiscal_year_keeps_latest_period_end():
    rows = [
        _row(2025, "2025-09-30", revenue=100.0),
        _row(2025, "2025-12-31", revenue=200.0),
    ]
    series = _Repo(rows).get_financial_timeseries("AAPL", years=10)

    assert series["revenue"][-1] == (2025, 200.0)


def test_timeseries_with_gaps_returns_none_not_exception():
    rows = [
        _row(2025, "2025-12-31", revenue=100.0),
        _row(2019, "2019-12-31", revenue=50.0),
    ]
    series = _Repo(rows).get_financial_timeseries("SKT", years=10)

    years = [year for year, _value in series["revenue"]]
    assert years == list(range(2016, 2026))
    assert dict(series["revenue"])[2020] is None
    assert dict(series["revenue"])[2019] == 50.0


def test_timeseries_empty_returns_all_fields_with_empty_lists():
    series = _Repo([]).get_financial_timeseries("NOPE", years=10)

    assert set(series) == set(FIELDS_OF_INTEREST)
    assert all(value == [] for value in series.values())
