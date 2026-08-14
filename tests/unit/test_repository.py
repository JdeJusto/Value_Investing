"""Unit tests for the financial repository implementations (no network)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.adapters.database.models.normalized import NormalizedFinancialModel
from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)
from backend.repositories.financial_repository import SqlAlchemyFinancialRepository
from backend.repositories.json_financial_repository import JsonFinancialRepository


def _record(ticker: str, year: int, revenue: float) -> NormalizedFinancials:
    return NormalizedFinancials(
        ticker=ticker,
        fiscal_year=year,
        revenue=revenue,
        net_income=revenue * 0.2,
        free_cash_flow=revenue * 0.1,
        shares_outstanding=1_000_000,
        source=ProviderName.YAHOO,
    )


@pytest.fixture
def json_repo(tmp_path):
    return JsonFinancialRepository(tmp_path / "normalized")


@pytest.fixture
def sql_repo():
    engine = create_engine("sqlite://")
    NormalizedFinancialModel.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    return SqlAlchemyFinancialRepository(factory)


@pytest.mark.parametrize("repo_fixture", ["json_repo", "sql_repo"])
def test_upsert_and_read(repo_fixture, request):
    repo = request.getfixturevalue(repo_fixture)
    repo.upsert(_record("AAPL", 2024, 391.0))

    record = repo.get_by_year("AAPL", 2024)
    assert record is not None
    assert record.revenue == 391.0
    assert record.source == ProviderName.YAHOO


@pytest.mark.parametrize("repo_fixture", ["json_repo", "sql_repo"])
def test_upsert_overwrites_same_year(repo_fixture, request):
    repo = request.getfixturevalue(repo_fixture)
    repo.upsert(_record("AAPL", 2024, 391.0))
    repo.upsert(_record("AAPL", 2024, 400.0))

    records = repo.list_years("AAPL")
    assert len(records) == 1
    assert records[0].revenue == 400.0


@pytest.mark.parametrize("repo_fixture", ["json_repo", "sql_repo"])
def test_list_years_sorted_desc(repo_fixture, request):
    repo = request.getfixturevalue(repo_fixture)
    repo.upsert_many(
        [
            _record("AAPL", 2022, 394.0),
            _record("AAPL", 2024, 391.0),
            _record("AAPL", 2023, 383.0),
        ]
    )

    years = [r.fiscal_year for r in repo.list_years("AAPL")]
    assert years == [2024, 2023, 2022]


@pytest.mark.parametrize("repo_fixture", ["json_repo", "sql_repo"])
def test_upsert_many_with_duplicates_in_batch(repo_fixture, request):
    """Duplicated keys inside one batch must collapse, not violate uniques."""
    repo = request.getfixturevalue(repo_fixture)
    repo.upsert_many(
        [
            _record("AAPL", 2024, 391.0),
            _record("AAPL", 2024, 400.0),
            _record("AAPL", 2024, 410.0),
        ]
    )

    records = repo.list_years("AAPL")
    assert len(records) == 1
    assert records[0].revenue == 410.0


@pytest.mark.parametrize("repo_fixture", ["json_repo", "sql_repo"])
def test_upsert_many_mixed_existing_and_new(repo_fixture, request):
    """Re-loading (years already stored) merges instead of duplicating."""
    repo = request.getfixturevalue(repo_fixture)
    repo.upsert_many([_record("AAPL", 2023, 383.0)])
    repo.upsert_many(
        [
            _record("AAPL", 2023, 385.0),
            _record("AAPL", 2024, 391.0),
        ]
    )

    records = {r.fiscal_year: r for r in repo.list_years("AAPL")}
    assert set(records) == {2023, 2024}
    assert records[2023].revenue == 385.0
    assert records[2024].revenue == 391.0


@pytest.mark.parametrize("repo_fixture", ["json_repo", "sql_repo"])
def test_has_data_and_delete(repo_fixture, request):
    repo = request.getfixturevalue(repo_fixture)
    assert repo.has_data("AAPL") is False

    repo.upsert(_record("AAPL", 2024, 391.0))
    assert repo.has_data("AAPL") is True

    repo.delete_ticker("AAPL")
    assert repo.has_data("AAPL") is False
    assert repo.list_years("AAPL") == []


@pytest.mark.parametrize("repo_fixture", ["json_repo", "sql_repo"])
def test_get_missing_year_returns_none(repo_fixture, request):
    repo = request.getfixturevalue(repo_fixture)
    assert repo.get_by_year("AAPL", 1999) is None


def test_json_repo_is_case_insensitive(json_repo):
    json_repo.upsert(_record("aapl", 2024, 391.0))
    assert json_repo.has_data("AAPL") is True
    assert json_repo.get_by_year("AAPL", 2024).ticker == "AAPL"


def test_json_repo_persists_across_instances(tmp_path):
    directory = tmp_path / "normalized"
    JsonFinancialRepository(directory).upsert(_record("AAPL", 2024, 391.0))

    reloaded = JsonFinancialRepository(directory)
    assert reloaded.get_by_year("AAPL", 2024).revenue == 391.0


def test_sql_repo_roundtrip_preserves_all_metrics(sql_repo):
    record = _record("GOOGL", 2023, 307.4)
    record.total_assets = 402.4
    record.total_liabilities = 115.2
    record.operating_cash_flow = 91.3
    sql_repo.upsert(record)

    restored = sql_repo.get_by_year("GOOGL", 2023)
    assert restored.total_assets == 402.4
    assert restored.total_liabilities == 115.2
    assert restored.operating_cash_flow == 91.3
    assert restored.free_cash_flow == record.free_cash_flow
