"""Unit tests for multi-source repository selection (no network)."""

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
from backend.repositories.source_selection import best_per_year, choose_history
from backend.providers.normalizers.quality import apply_quality_metrics


def _record(
    year: int,
    source: ProviderName = ProviderName.YAHOO,
    revenue: float = 100.0,
    complete: bool = True,
    derived: bool = True,
) -> NormalizedFinancials:
    record = NormalizedFinancials(
        ticker="AAPL",
        fiscal_year=year,
        source=source,
        revenue=revenue,
        net_income=20.0 if complete else None,
        total_assets=300.0 if complete else None,
        shares_outstanding=1_000_000 if complete else None,
        free_cash_flow=15.0 if derived else None,
        ebitda=30.0 if derived else None,
    )
    return apply_quality_metrics(record)


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
def test_multiple_sources_per_year_stored(repo_fixture, request):
    repo = request.getfixturevalue(repo_fixture)
    repo.upsert(_record(2025, ProviderName.YAHOO))
    repo.upsert(_record(2025, ProviderName.EDGAR))

    rows = repo.list_all("AAPL")
    assert len(rows) == 2
    assert {r.source for r in rows} == {ProviderName.YAHOO, ProviderName.EDGAR}


@pytest.mark.parametrize("repo_fixture", ["json_repo", "sql_repo"])
def test_upsert_same_source_overwrites(repo_fixture, request):
    repo = request.getfixturevalue(repo_fixture)
    repo.upsert(_record(2025, ProviderName.YAHOO, revenue=100.0))
    repo.upsert(_record(2025, ProviderName.YAHOO, revenue=150.0))

    rows = repo.list_all("AAPL")
    assert len(rows) == 1
    assert rows[0].revenue == 150.0


@pytest.mark.parametrize("repo_fixture", ["json_repo", "sql_repo"])
def test_get_by_year_prefers_higher_priority_source(repo_fixture, request):
    repo = request.getfixturevalue(repo_fixture)
    edgar = _record(2025, ProviderName.EDGAR)
    edgar.data_quality_score = 0.99  # edgar record is top quality
    repo.upsert(edgar)
    repo.upsert(_record(2025, ProviderName.YAHOO))

    best = repo.get_by_year("AAPL", 2025)
    assert best.source == ProviderName.YAHOO


@pytest.mark.parametrize("repo_fixture", ["json_repo", "sql_repo"])
def test_get_best_available_prefers_single_consistent_source(repo_fixture, request):
    repo = request.getfixturevalue(repo_fixture)
    # Yahoo covers all 3 years (even if "incomplete-ish" quality); EDGAR only 1
    for year in (2023, 2024, 2025):
        repo.upsert(_record(year, ProviderName.YAHOO))
    repo.upsert(_record(2025, ProviderName.EDGAR))

    selected = repo.get_best_available("AAPL")

    assert [r.fiscal_year for r in selected] == [2025, 2024, 2023]
    assert {r.source for r in selected} == {ProviderName.YAHOO}


@pytest.mark.parametrize("repo_fixture", ["json_repo", "sql_repo"])
def test_get_best_available_blends_when_no_consistency(repo_fixture, request):
    repo = request.getfixturevalue(repo_fixture)
    # Yahoo only covers 1 of 3 years
    repo.upsert(_record(2025, ProviderName.YAHOO))
    repo.upsert(_record(2024, ProviderName.EDGAR))
    repo.upsert(_record(2023, ProviderName.EDGAR))

    selected = repo.get_best_available("AAPL")

    assert len(selected) == 3
    assert {r.source for r in selected} == {ProviderName.YAHOO, ProviderName.EDGAR}
    by_year = {r.fiscal_year: r for r in selected}
    assert by_year[2025].source == ProviderName.YAHOO
    assert by_year[2024].source == ProviderName.EDGAR


def test_choose_history_uses_priority_then_coverage_then_quality():
    rows = [
        _record(2025, ProviderName.YAHOO, complete=False, derived=False),
        _record(2024, ProviderName.YAHOO, complete=False, derived=False),
        _record(2023, ProviderName.YAHOO, complete=False, derived=False),
        _record(2025, ProviderName.EDGAR, complete=True, derived=True),
    ]
    selected = choose_history(rows)
    assert {r.source for r in selected} == {ProviderName.YAHOO}


def test_choose_history_favours_full_edgar_when_yahoo_sparse():
    rows = [
        _record(2025, ProviderName.YAHOO),
        _record(2025, ProviderName.EDGAR),
        _record(2024, ProviderName.EDGAR),
        _record(2023, ProviderName.EDGAR),
    ]
    selected = choose_history(rows)
    assert {r.source for r in selected} == {ProviderName.EDGAR}
    assert len(selected) == 3


def test_best_per_year_never_mixes_within_year():
    rows = [
        _record(2025, ProviderName.YAHOO),
        _record(2025, ProviderName.EDGAR),
        _record(2024, ProviderName.EDGAR),
    ]
    selected = best_per_year(rows)
    assert len(selected) == 2
    assert selected[0].source == ProviderName.YAHOO  # 2025
    assert selected[1].source == ProviderName.EDGAR  # 2024


def test_quality_fields_roundtrip_through_sqlite(sql_repo):
    record = _record(2025, ProviderName.EDGAR)
    record.derived_metrics = ["free_cash_flow"]
    sql_repo.upsert(record)

    restored = sql_repo.get_by_year("AAPL", 2025)
    assert restored.data_quality_score == record.data_quality_score
    assert restored.data_completeness == record.data_completeness
    assert restored.is_complete == record.is_complete
    assert restored.data_source_priority == record.data_source_priority
    assert restored.derived_metrics == ["free_cash_flow"]


def test_quality_fields_roundtrip_through_json(json_repo):
    record = _record(2025, ProviderName.EDGAR)
    record.derived_metrics = ["free_cash_flow"]
    json_repo.upsert(record)

    restored = json_repo.get_by_year("AAPL", 2025)
    assert restored.data_quality_score == record.data_quality_score
    assert restored.derived_metrics == ["free_cash_flow"]
    assert restored.source == ProviderName.EDGAR


def test_json_legacy_single_source_format_migrates(tmp_path):
    import json

    directory = tmp_path / "normalized"
    directory.mkdir()
    legacy = {
        "ticker": "AAPL",
        "years": {
            "2025": {
                "ticker": "AAPL",
                "fiscal_year": 2025,
                "source": "yahoo",
                "revenue": 100.0,
                "data_quality_score": 0.9,
                "data_completeness": 1.0,
                "is_complete": True,
                "data_source_priority": 2,
                "derived_metrics": [],
                "loaded_at": "2026-08-01T00:00:00+00:00",
            }
        },
    }
    (directory / "AAPL.json").write_text(json.dumps(legacy))

    repo = JsonFinancialRepository(directory)
    rows = repo.list_all("AAPL")
    assert len(rows) == 1
    assert rows[0].source == ProviderName.YAHOO
    assert rows[0].revenue == 100.0

    # re-saving must keep working in the new multi-source shape
    repo.upsert(_record(2025, ProviderName.EDGAR))
    assert len(repo.list_all("AAPL")) == 2
