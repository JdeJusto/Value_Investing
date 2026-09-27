"""Unit tests for the targeted catch-up tool (scripts/catch_up_stale.py).

The tool must never become a database-wide sweep: it selects a bounded,
ranked set of stale companies and syncs one CIK at a time through the
Financial-DataBase CLI. These tests pin the selection, the bounds, the
priority order and the guardrails (preflight, --limit, --dry-run).
"""

from __future__ import annotations

import pytest

from backend.services.refresh_service import FdbGateway
from scripts import catch_up_stale


class _Row(dict):
    """A stale-company row as FdbGateway returns it."""


def _rows(count: int) -> list[_Row]:
    return [
        _Row(
            company_id=f"company-{i:03d}",
            cik=f"{i:010d}",
            legal_name=f"Company {i:03d} Inc",
            last_synced_at=None if i % 5 == 0 else "2026-09-06 20:00:00+00",
            last_filing=f"2026-09-2{i % 9}T00:00:00+00",
            filing_count=100 + i,
        )
        for i in range(count)
    ]


class _FakeGateway:
    def __init__(self, rows=None, available: bool = True):
        self._rows = rows if rows is not None else _rows(10)
        self._available = available
        self.calls: list[dict] = []

    def available(self) -> bool:
        return self._available

    def stale_companies(self, *, max_age_hours=None, limit=500, priority="recent_filings"):
        self.calls.append(
            {"max_age_hours": max_age_hours, "limit": limit, "priority": priority}
        )
        return self._rows[:limit]


class _FakeService:
    def __init__(self, results=None):
        self.results = results or {}
        self.synced: list[str] = []

    def sync_one(self, cik: str):
        self.synced.append(cik)
        return self.results.get(cik, True)


@pytest.fixture
def _patched(monkeypatch):
    """Wire the tool's collaborators with fakes; returns the recorded calls."""
    recorded: dict = {}

    def _install(gateway=None, service=None, health_available=True, has_ua=True):
        gateway = gateway if gateway is not None else _FakeGateway()
        service = service if service is not None else _FakeService()
        monkeypatch.setattr(catch_up_stale, "FdbGateway", lambda *a, **k: gateway)
        monkeypatch.setattr(catch_up_stale, "RefreshService", lambda *a, **k: service)
        monkeypatch.setattr(
            catch_up_stale,
            "check_sec_availability",
            lambda *a, **k: type(
                "H", (), {"available": health_available, "reason": "probe"}
            )(),
        )
        if has_ua:
            monkeypatch.setenv("SEC_USER_AGENT", "Tool/1.0 someone@example.com")
        else:
            monkeypatch.delenv("SEC_USER_AGENT", raising=False)
        recorded["gateway"] = gateway
        recorded["service"] = service
        return recorded

    return _install


# ----------------------------------------------------------------------
# selection
# ----------------------------------------------------------------------


def test_dry_run_never_syncs_and_lists_the_selection(_patched, capsys):
    recorded = _patched()
    exit_code = catch_up_stale.main(["--limit", "5", "--dry-run", "--show", "5"])

    assert exit_code == 0
    assert recorded["service"].synced == []
    out = capsys.readouterr().out
    assert "DRY-RUN: no SEC request was made." in out
    assert "Company 000 Inc" in out
    assert "priority=recent_filings" in out


def test_limit_is_passed_through_and_bounded(_patched):
    recorded = _patched()
    catch_up_stale.main(["--limit", "7", "--dry-run", "--show", "0"])

    assert recorded["gateway"].calls == [
        {"max_age_hours": 168, "limit": 7, "priority": "recent_filings"}
    ]


def test_limit_must_be_positive(_patched, capsys):
    _patched()
    exit_code = catch_up_stale.main(["--limit", "0", "--dry-run"])

    assert exit_code == 2
    assert "always bounded" in capsys.readouterr().err


def test_all_three_priorities_are_accepted(_patched):
    recorded = _patched()
    for priority in ("recent_filings", "alphabetical", "random"):
        assert catch_up_stale.main(["--limit", "2", "--dry-run", "--priority", priority]) == 0

    assert [call["priority"] for call in recorded["gateway"].calls] == [
        "recent_filings",
        "alphabetical",
        "random",
    ]


def test_unknown_priority_is_rejected_by_the_parser(capsys):
    with pytest.raises(SystemExit):
        catch_up_stale.main(["--priority", "whatever"])


def test_freshness_hours_is_configurable(_patched):
    recorded = _patched()
    catch_up_stale.main(["--limit", "1", "--dry-run", "--freshness-hours", "48"])

    assert recorded["gateway"].calls[0]["max_age_hours"] == 48


def test_nothing_to_do_is_a_clean_exit(_patched, capsys):
    _patched(gateway=_FakeGateway(rows=[]))
    exit_code = catch_up_stale.main(["--limit", "5", "--dry-run"])

    assert exit_code == 0
    assert "nothing to do" in capsys.readouterr().out


def test_unreachable_database_exits_with_an_error(_patched, capsys):
    _patched(gateway=_FakeGateway(available=False))
    exit_code = catch_up_stale.main(["--limit", "5", "--dry-run"])

    assert exit_code == 2
    assert "unreachable" in capsys.readouterr().err


# ----------------------------------------------------------------------
# guardrails and execution
# ----------------------------------------------------------------------


def test_syncs_every_selected_company_individually(_patched, capsys):
    recorded = _patched()
    exit_code = catch_up_stale.main(["--limit", "4", "--show", "0"])

    assert exit_code == 0
    # one targeted sync per company, in CIK order of the selection
    assert recorded["service"].synced == [
        f"{i:010d}" for i in range(4)
    ]
    assert "4 synced, 0 failed" in capsys.readouterr().out


def test_sec_preflight_failure_stops_before_any_sync(_patched, capsys):
    recorded = _patched(health_available=False)
    exit_code = catch_up_stale.main(["--limit", "3", "--show", "0"])

    assert exit_code == 3
    assert recorded["service"].synced == []
    assert "Nothing was synced" in capsys.readouterr().err


def test_missing_user_agent_is_reported_not_attempted(_patched, capsys):
    recorded = _patched(has_ua=False)
    exit_code = catch_up_stale.main(["--limit", "3", "--show", "0"])

    assert exit_code == 2
    assert recorded["service"].synced == []
    assert "SEC_USER_AGENT" in capsys.readouterr().err


def test_failures_are_reported_with_a_non_zero_exit(_patched, capsys):
    service = _FakeService(results={"0000000002": "SEC sync failed (HTTP 403)"})
    recorded = _patched(service=service)
    exit_code = catch_up_stale.main(["--limit", "3", "--show", "0"])

    assert exit_code == 1
    assert len(recorded["service"].synced) == 3  # every company was attempted
    out = capsys.readouterr().out
    assert "2 synced, 1 failed" in out
    assert "HTTP 403" in out


def test_selection_query_is_read_only_and_company_scoped():
    """The gateway query must never touch import_runs or prices."""
    import inspect

    source = inspect.getsource(FdbGateway.stale_companies).lower()
    for forbidden in ("insert", "update ", "delete", "prices", "import_runs"):
        assert forbidden not in source
