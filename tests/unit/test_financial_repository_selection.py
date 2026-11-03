"""Repository selection: an unreachable Financial-DataBase must be loud.

Before this guard, a boot-time race fell through to the legacy JSON store
(45% usable coverage) while the run still looked healthy. ``VI_REQUIRE_FDB``
turns that into a hard failure and the fallback path logs an error.
"""

from __future__ import annotations

import pytest

from backend.repositories.json_financial_repository import JsonFinancialRepository


class _UnavailableFdb:
    def __init__(self, *args, **kwargs):
        pass

    def available(self, **kwargs):
        return False


class _UnavailableSql:
    def __init__(self, *args, **kwargs):
        pass

    def available(self):
        return False


def _clear_repository_env(monkeypatch) -> None:
    monkeypatch.delenv("VI_DEMO", raising=False)
    monkeypatch.delenv("VI_REQUIRE_FDB", raising=False)
    monkeypatch.delenv("FDB_READY_TIMEOUT_SECONDS", raising=False)


def test_require_fdb_raises_instead_of_json_fallback(monkeypatch):
    _clear_repository_env(monkeypatch)
    monkeypatch.setenv("VI_REQUIRE_FDB", "1")
    monkeypatch.setattr("backend.app.cli.FinancialDatabaseRepository", _UnavailableFdb)

    from backend.app.cli import build_financial_repository

    with pytest.raises(RuntimeError, match="VI_REQUIRE_FDB"):
        build_financial_repository()


def test_json_fallback_is_logged_as_an_error(monkeypatch, caplog):
    _clear_repository_env(monkeypatch)
    monkeypatch.setattr("backend.app.cli.FinancialDatabaseRepository", _UnavailableFdb)
    monkeypatch.setattr(
        "backend.repositories.financial_repository.SqlAlchemyFinancialRepository",
        _UnavailableSql,
    )

    from backend.app.cli import build_financial_repository

    with caplog.at_level("ERROR"):
        repository = build_financial_repository()

    assert isinstance(repository, JsonFinancialRepository)
    assert "legacy JSON store" in caplog.text
