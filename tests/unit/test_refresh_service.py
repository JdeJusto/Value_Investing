"""Unit tests for the on-demand SEC refresh service.

The refresh step is the single integration point between Value Investing
analysis commands and Financial-DataBase ingestion: stale companies get a
targeted ``sec sync <CIK>`` before analysis, and real-time prices are
returned without ever being persisted.

These tests are hermetic: a fake gateway stands in for Financial-DataBase
and a fake price service for PriceService, so no DB or network is needed.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest

from backend.services.refresh_service import (
    DEFAULT_FRESHNESS_MAX_AGE_HOURS,
    FdbGateway,
    RefreshConfig,
    RefreshService,
    load_refresh_config,
)

NOW = dt.datetime.now(dt.timezone.utc)
STALE = NOW - dt.timedelta(hours=200)  # older than the 168h threshold
FRESH = NOW - dt.timedelta(hours=10)


class FakeGateway:
    """Read-only Financial-DataBase stand-in (records every read)."""

    def __init__(self, companies=None, last_synced=None, available=True):
        self.companies = companies or {}  # ticker -> (company_id, cik)
        self._last_synced = last_synced or {}  # company_id -> datetime
        self._available = available
        self.available_calls = 0
        self.resolve_calls: list[str] = []
        self.last_synced_calls: list[str] = []

    def available(self) -> bool:
        self.available_calls += 1
        return self._available

    def resolve_company(self, ticker: str):
        self.resolve_calls.append(ticker)
        return self.companies.get(ticker)

    def last_synced_at(self, company_id: str):
        self.last_synced_calls.append(company_id)
        return self._last_synced.get(company_id)

    def close(self) -> None:
        pass


class FakePriceService:
    """In-memory price stand-in; proves prices never touch the DB."""

    def __init__(self, prices=None):
        self.prices = prices or {}
        self.calls: list[list[str]] = []

    def get_current_prices(self, tickers, batch_size=25, delay=0.2):
        self.calls.append(list(tickers))
        return {t: self.prices.get(t) for t in tickers}


def make_service(gateway=None, price=None, runner=None, config=None, **kwargs):
    return RefreshService(
        config=config or RefreshConfig(),
        gateway=gateway or FakeGateway(),
        price_service=price or FakePriceService(),
        sync_runner=runner,
        **kwargs,
    )


# ----------------------------------------------------------------------
# config loading
# ----------------------------------------------------------------------


def test_load_config_defaults(monkeypatch):
    for var in ("REFRESH_AUTO", "FRESHNESS_MAX_AGE_HOURS",
                "REFRESH_TIMEOUT_SECONDS", "REFRESH_SKIP_FLAG"):
        monkeypatch.delenv(var, raising=False)
    cfg = load_refresh_config("/nonexistent/refresh.yaml")
    assert cfg.auto_refresh is True
    assert cfg.freshness_max_age_hours == DEFAULT_FRESHNESS_MAX_AGE_HOURS
    assert cfg.refresh_timeout_seconds == 300
    assert cfg.skip_refresh_flag is False


def test_load_config_from_file(tmp_path, monkeypatch):
    for var in ("REFRESH_AUTO", "FRESHNESS_MAX_AGE_HOURS",
                "REFRESH_TIMEOUT_SECONDS", "REFRESH_SKIP_FLAG"):
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "refresh.yaml"
    path.write_text(
        "# comment\n"
        "auto_refresh: false\n"
        "freshness_max_age_hours: 24\n"
        "refresh_timeout_seconds: 60\n"
        "skip_refresh_flag: true\n"
    )
    cfg = load_refresh_config(str(path))
    assert cfg.auto_refresh is False
    assert cfg.freshness_max_age_hours == 24
    assert cfg.refresh_timeout_seconds == 60
    assert cfg.skip_refresh_flag is True


def test_env_overrides_file(tmp_path, monkeypatch):
    path = tmp_path / "refresh.yaml"
    path.write_text("freshness_max_age_hours: 24\n")
    monkeypatch.setenv("FRESHNESS_MAX_AGE_HOURS", "12")
    cfg = load_refresh_config(str(path))
    assert cfg.freshness_max_age_hours == 12


# ----------------------------------------------------------------------
# targeted refresh decisions
# ----------------------------------------------------------------------


def test_stale_company_triggers_targeted_sync():
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193")},
        last_synced={"c1": STALE},
    )
    runner_ciks = []
    service = make_service(gateway=gateway, runner=lambda cik: runner_ciks.append(cik) or True)

    result = service.ensure_fresh_and_prices(["AAPL"], fetch_prices=False)

    assert result.refreshed == ["AAPL"]
    assert result.failed == []
    assert runner_ciks == ["0000320193"]  # targeted per-CIK sync


def test_fresh_company_is_skipped():
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193")},
        last_synced={"c1": FRESH},
    )
    runner_ciks = []
    service = make_service(gateway=gateway, runner=lambda cik: runner_ciks.append(cik) or True)

    result = service.ensure_fresh_and_prices(["AAPL"], fetch_prices=False)

    assert result.skipped == ["AAPL"]
    assert result.refreshed == []
    assert runner_ciks == []


def test_never_synced_company_is_refreshed():
    gateway = FakeGateway(companies={"AAPL": ("c1", "0000320193")}, last_synced={})
    runner_ciks = []
    service = make_service(gateway=gateway, runner=lambda cik: runner_ciks.append(cik) or True)

    result = service.ensure_fresh_and_prices(["AAPL"], fetch_prices=False)

    assert result.refreshed == ["AAPL"]


def test_force_refreshes_regardless_of_age():
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193")},
        last_synced={"c1": FRESH},
    )
    runner_ciks = []
    service = make_service(gateway=gateway, runner=lambda cik: runner_ciks.append(cik) or True)

    result = service.ensure_fresh_and_prices(["AAPL"], force=True, fetch_prices=False)

    assert result.refreshed == ["AAPL"]
    assert runner_ciks == ["0000320193"]


def test_freshness_hours_override():
    # FRESH is 10h old; with a 1h threshold it must be refreshed.
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193")},
        last_synced={"c1": FRESH},
    )
    runner_ciks = []
    service = make_service(gateway=gateway, runner=lambda cik: runner_ciks.append(cik) or True)

    result = service.ensure_fresh_and_prices(
        ["AAPL"], max_age_hours=1, fetch_prices=False
    )

    assert result.refreshed == ["AAPL"]
    assert runner_ciks == ["0000320193"]


def test_no_cik_mapping_is_reported_not_fatal():
    gateway = FakeGateway(companies={"ZZZZZZ": None})
    service = make_service(gateway=gateway, runner=lambda cik: True)

    result = service.ensure_fresh_and_prices(["ZZZZZZ"], fetch_prices=False)

    assert result.failed == [("ZZZZZZ", "no CIK mapping in Financial-DataBase")]
    assert result.refreshed == []
    assert result.skipped == []


def test_unknown_tickers_do_not_crash():
    gateway = FakeGateway(companies={"AAPL": ("c1", "0000320193")})
    service = make_service(gateway=gateway, runner=lambda cik: True)

    result = service.ensure_fresh_and_prices(["  aapl ", "ZZZZZZ"], fetch_prices=False)

    assert result.refreshed == ["AAPL"]
    assert result.failed == [("ZZZZZZ", "no CIK mapping in Financial-DataBase")]


# ----------------------------------------------------------------------
# skipping / degradation
# ----------------------------------------------------------------------


def test_skip_refresh_does_no_db_work_but_still_prices():
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193")},
        last_synced={"c1": STALE},
    )
    price = FakePriceService(prices={"AAPL": 123.45})
    service = make_service(gateway=gateway, price=price, runner=lambda cik: True)

    result = service.ensure_fresh_and_prices(["AAPL"], skip_refresh=True)

    assert result.skipped == ["AAPL"]
    assert result.refreshed == []
    assert gateway.resolve_calls == []  # no DB work when sync is disabled
    assert gateway.last_synced_calls == []
    assert result.prices == {"AAPL": 123.45}
    assert price.calls == [["AAPL"]]


def test_fdb_unavailable_degrades_gracefully():
    gateway = FakeGateway(available=False)
    price = FakePriceService(prices={"AAPL": 99.0})
    service = make_service(gateway=gateway, price=price, runner=lambda cik: True)

    result = service.ensure_fresh_and_prices(["AAPL", "MSFT"])

    assert result.failed == []
    assert set(result.skipped) == {"AAPL", "MSFT"}
    assert any("unreachable" in n for n in result.notes)
    assert result.prices == {"AAPL": 99.0, "MSFT": None}


def test_sync_failure_is_reported_not_fatal(monkeypatch):
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193")},
        last_synced={"c1": STALE},
    )
    service = make_service(gateway=gateway, runner=lambda cik: "boom: SEC down")

    result = service.ensure_fresh_and_prices(["AAPL"], fetch_prices=False)

    assert result.failed == [("AAPL", "boom: SEC down")]
    assert result.refreshed == []


def test_missing_sec_user_agent_degrades_gracefully(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193")},
        last_synced={"c1": STALE},
    )
    price = FakePriceService(prices={"AAPL": 123.0})
    service = make_service(
        gateway=gateway, price=price, fdb_repo_path="/nonexistent/repo"
    )

    # No runner injected -> exercises the real _run_fdb_cli early-return.
    result = service.ensure_fresh_and_prices(["AAPL"])

    assert len(result.failed) == 1
    assert "SEC_USER_AGENT" in result.failed[0][1]
    assert result.prices == {"AAPL": 123.0}  # prices still usable


def test_unrunnable_fdb_cli_degrades_gracefully(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TestApp/1.0 tester@example.com")
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193")},
        last_synced={"c1": STALE},
    )
    service = make_service(
        gateway=gateway, fdb_repo_path="/nonexistent/repo"
    )

    result = service.ensure_fresh_and_prices(["AAPL"], fetch_prices=False)

    assert len(result.failed) == 1
    assert "not runnable" in result.failed[0][1]


# ----------------------------------------------------------------------
# prices are never persisted
# ----------------------------------------------------------------------


def test_prices_come_from_price_service_never_the_gateway():
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193"), "MSFT": ("c2", "0000789019")},
        last_synced={"c1": FRESH, "c2": FRESH},
    )
    price = FakePriceService(prices={"AAPL": 111.0, "MSFT": 222.0})
    service = make_service(gateway=gateway, price=price)

    result = service.ensure_fresh_and_prices(["AAPL", "MSFT"])

    # Prices come out of the in-memory price service only; the gateway was
    # only ever read for freshness metadata (no write methods exist).
    assert result.prices == {"AAPL": 111.0, "MSFT": 222.0}
    assert gateway.resolve_calls == ["AAPL", "MSFT"]
    assert sorted(gateway.last_synced_calls) == ["c1", "c2"]
    assert price.calls == [["AAPL", "MSFT"]]


def test_database_url_default_matches_repository():
    # The refresh gateway defaults to the same Financial-DataBase URL as the
    # FinancialDatabaseRepository so the two always talk to the same DB.
    repo = FdbGateway()
    assert "financial_database" in repo.database_url
    assert os.environ.get("FINANCIAL_DATABASE_URL", "financial_database") in repo.database_url


# ----------------------------------------------------------------------
# check_freshness (read-only scope estimation, used by the daily workflow)
# ----------------------------------------------------------------------


def test_check_freshness_splits_stale_fresh_unknown():
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193"), "KO": ("c2", "0000021344"),
                   "MSFT": ("c3", "0000789019")},
        last_synced={"c1": STALE, "c2": FRESH, "c3": STALE},
    )
    service = make_service(gateway=gateway)

    stale, fresh, unknown = service.check_freshness(
        ["AAPL", "ko", "MSFT", "NOPE"]
    )

    assert stale == ["AAPL", "MSFT"]
    assert fresh == ["KO"]
    assert unknown == ["NOPE"]
    # Read-only: never resolves the sync runner / never refetches prices.
    assert gateway.resolve_calls == ["AAPL", "KO", "MSFT", "NOPE"]
    assert sorted(gateway.last_synced_calls) == ["c1", "c2", "c3"]


def test_check_freshness_never_synced_is_stale():
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193")},
        last_synced={},
    )
    service = make_service(gateway=gateway)

    stale, fresh, unknown = service.check_freshness(["AAPL", "aapl"])

    assert stale == ["AAPL"]  # deduplicated, untouched company is stale
    assert fresh == []
    assert unknown == []


def test_check_freshness_dedup_and_threshold_override():
    gateway = FakeGateway(
        companies={"AAPL": ("c1", "0000320193"), "MSFT": ("c2", "0000789019")},
        last_synced={"c1": FRESH, "c2": STALE},
    )
    service = make_service(gateway=gateway)

    stale, fresh, _ = service.check_freshness(
        ["AAPL", "MSFT", "AAPL"], max_age_hours=5
    )

    # With a 5h threshold, even the 10h-old data is stale.
    assert stale == ["AAPL", "MSFT"]
    assert fresh == []
    assert gateway.resolve_calls == ["AAPL", "MSFT"]


def test_check_freshness_db_down_lists_everything_unknown():
    gateway = FakeGateway(available=False)
    service = make_service(gateway=gateway)

    stale, fresh, unknown = service.check_freshness(["AAPL", "MSFT"])

    assert stale == []
    assert fresh == []
    assert unknown == ["AAPL", "MSFT"]