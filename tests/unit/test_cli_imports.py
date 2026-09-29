"""Unit tests for the app/cli.py import fix and the narrowed except clauses.

The repository is monkeypatched in its own module: the CLI imports it lazily
inside the two functions, so the patch resolves at call time. No database.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.app import cli
from backend.domain.entities.company import Company
from backend.providers.tickers import TICKERS

_REPO = "backend.adapters.database.repositories.company_repository.CompanyRepository"


def test_import_does_not_raise():
    # Importing the module is the assertion: no NameError at import time.
    assert cli is not None


def test_tracked_tickers_uses_repository(monkeypatch):
    class _Repo:
        def list_all(self):
            return [Company(ticker="ZZZ"), Company(ticker="YYY")]

    monkeypatch.setattr(_REPO, _Repo)
    assert cli._tracked_tickers() == ["ZZZ", "YYY"]


def test_tracked_tickers_falls_back_on_db_error(monkeypatch):
    class _Down:
        def list_all(self):
            raise SQLAlchemyError("database down")

    monkeypatch.setattr(_REPO, _Down)
    assert cli._tracked_tickers() == TICKERS


def test_name_errors_are_not_swallowed(monkeypatch):
    class _Boom:
        def list_all(self):
            raise NameError("boom")

    monkeypatch.setattr(_REPO, _Boom)
    with pytest.raises(NameError):
        cli._tracked_tickers()


def test_company_enrichment_sets_sector(monkeypatch):
    class _Repo:
        def find_by_ticker(self, ticker):
            return Company(ticker=ticker, sector="Technology", industry="Software")

    monkeypatch.setattr(_REPO, _Repo)
    item = cli._company_enrichment()("AAPL", {})
    assert item["sector"] == "Technology"
    assert item["industry"] == "Software"


def test_company_enrichment_falls_back_on_db_error(monkeypatch):
    class _Down:
        def find_by_ticker(self, ticker):
            raise SQLAlchemyError("down")

    monkeypatch.setattr(_REPO, _Down)
    item = cli._company_enrichment()("AAPL", {})
    assert item == {}
