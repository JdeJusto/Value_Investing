"""Unit tests for the SEC contact handling in the service builders.

The contact e-mail is personal data: it lives in the git-ignored .env and is
never hardcoded. These tests pin the two behaviours that matter — an
configured contact still builds the live EDGAR fallback, and a missing one
disables that fallback with a warning instead of breaking every command that
happens to build the pipeline (fundamentals come from Financial-DataBase).
"""

from __future__ import annotations

import logging

import pytest

from backend.config.settings import get_sec_email
from backend.app import cli as app_cli


@pytest.fixture
def _no_sec_email(monkeypatch):
    monkeypatch.delenv("SEC_EMAIL", raising=False)
    monkeypatch.setattr(app_cli, "sec_email", "", raising=False)


def test_get_sec_email_returns_the_environment_value(monkeypatch):
    monkeypatch.setenv("SEC_EMAIL", "someone@example.com")
    assert get_sec_email() == "someone@example.com"


def test_get_sec_email_fails_fast_with_an_actionable_message(monkeypatch):
    monkeypatch.delenv("SEC_EMAIL", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        get_sec_email()
    message = str(excinfo.value)
    assert "SEC_EMAIL" in message
    assert ".env" in message
    assert "403" in message  # why an unattributed request fails


def test_module_level_contact_comes_only_from_the_environment(monkeypatch):
    monkeypatch.delenv("SEC_EMAIL", raising=False)
    monkeypatch.delenv("SEC_NAME", raising=False)
    import importlib

    reloaded = importlib.reload(app_cli)
    try:
        assert reloaded.sec_email == ""
        assert reloaded.sec_name  # a non-empty default name, never a person
    finally:
        monkeypatch.setenv("SEC_EMAIL", "someone@example.com")
        importlib.reload(app_cli)


def test_pipeline_without_a_contact_disables_edgar_and_warns(
    _no_sec_email, monkeypatch, caplog
):
    """A missing SEC_EMAIL must not break FDB-backed commands."""
    from backend.services.data_pipeline_service import DataPipelineService

    created: dict = {}

    class _StubEdgar:
        def __init__(self, email, name):
            created["email"] = email

    monkeypatch.setattr("backend.providers.edgar.EdgarProvider", _StubEdgar)
    monkeypatch.setattr(
        "backend.providers.yahoo.YahooFinanceProvider", lambda *a, **k: object()
    )

    with caplog.at_level(logging.WARNING):
        service = app_cli.build_data_pipeline()

    assert isinstance(service, DataPipelineService)
    assert service._fallback is None  # live EDGAR disabled, not crashed
    assert "email" not in created  # no unattributed provider was built
    assert any("SEC_EMAIL" in record.message % record.args for record in caplog.records)


def test_pipeline_with_a_contact_builds_the_edgar_fallback(monkeypatch):
    from backend.services.data_pipeline_service import DataPipelineService

    created: dict = {}

    class _StubEdgar:
        def __init__(self, email, name):
            created["email"] = email
            created["name"] = name

    monkeypatch.setattr(app_cli, "sec_email", "someone@example.com", raising=False)
    monkeypatch.setattr(app_cli, "sec_name", "Someone", raising=False)
    monkeypatch.setattr("backend.providers.edgar.EdgarProvider", _StubEdgar)
    monkeypatch.setattr(
        "backend.providers.yahoo.YahooFinanceProvider", lambda *a, **k: object()
    )

    service = app_cli.build_data_pipeline()

    assert isinstance(service, DataPipelineService)
    assert service._fallback is not None
    assert created["email"] == "someone@example.com"
