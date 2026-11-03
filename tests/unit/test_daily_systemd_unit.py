"""The daily systemd unit must not start before PostgreSQL and DNS are ready."""

from __future__ import annotations

from pathlib import Path

UNIT = (
    Path(__file__).resolve().parents[2]
    / "deploy"
    / "systemd"
    / "value-investing-daily.service"
)


def _unit_text() -> str:
    return UNIT.read_text(encoding="utf-8")


def test_unit_waits_for_postgres_and_dns():
    text = _unit_text()
    assert "ExecStartPre=" in text
    assert "pg_isready -h 127.0.0.1 -p 5432" in text
    assert "getent hosts data.sec.gov" in text
    assert "getent hosts query1.finance.yahoo.com" in text


def test_unit_uses_loopback_and_requires_fdb():
    text = _unit_text()
    assert (
        "FINANCIAL_DATABASE_URL=postgresql://financial@127.0.0.1:5432/"
        "financial_database" in text
    )
    assert "VI_REQUIRE_FDB=1" in text
    assert "FDB_READY_TIMEOUT_SECONDS=60" in text
