"""``FinancialDatabaseRepository.available`` readiness probing.

The daily systemd timer fires seconds after boot, while PostgreSQL may still
be starting. The probe must retry and log instead of returning a silent False
(which used to send the run to the legacy JSON store).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import psycopg2

from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)


def _connection() -> MagicMock:
    conn = MagicMock()
    conn.closed = 0
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


def test_available_retries_until_postgres_is_ready(monkeypatch):
    calls = {"count": 0}

    def connect(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise psycopg2.OperationalError("the database system is starting up")
        return _connection()

    monkeypatch.setattr(
        "backend.repositories.financial_database_repository.psycopg2.connect",
        connect,
    )

    repository = FinancialDatabaseRepository()

    assert repository.available(retries=2, retry_delay_s=0) is True
    assert calls["count"] == 3


def test_available_logs_exhausted_retries(monkeypatch, caplog):
    def connect(*args, **kwargs):
        raise psycopg2.OperationalError("connection refused")

    monkeypatch.setattr(
        "backend.repositories.financial_database_repository.psycopg2.connect",
        connect,
    )

    repository = FinancialDatabaseRepository()

    with caplog.at_level("ERROR"):
        assert repository.available(retries=1, retry_delay_s=0) is False

    assert "unavailable after 2 attempt" in caplog.text
    assert "connection refused" in caplog.text
