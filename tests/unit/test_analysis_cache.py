"""Unit tests for the fundamentals analysis cache (Phase 3).

The cache stores normalized fundamentals rows per ticker and reuses them only
while both the fundamentals fingerprint and the analysis version match, so a
new filing or a logic change forces a recompute while a pure price move does
not (price metrics are always recomputed by the analysis service).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

import pytest

from backend.analytics.service import CompanyAnalysisService
from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)
from backend.services.analysis_cache import AnalysisCache, ANALYSIS_VERSION


def _row(year: int, revenue: float | None = 100.0) -> NormalizedFinancials:
    # DB-backed rows always carry loaded_at (that is what is_stale checks);
    # without it the service would ask the repository again.
    return NormalizedFinancials(
        ticker="AAPL",
        fiscal_year=year,
        source=ProviderName.EDGAR,
        revenue=revenue,
        net_income=20.0,
        total_assets=300.0,
        total_liabilities=120.0,
        free_cash_flow=25.0,
        loaded_at=datetime.now(timezone.utc),
    )


class _Repo:
    """Repository stand-in exposing only the fingerprint hook."""

    def __init__(self, fingerprint: str | None = "fp-1"):
        self.fingerprint = fingerprint
        self.fp_calls = 0
        self.read_calls = 0

    def fundamentals_fingerprint(self, ticker: str) -> str | None:
        self.fp_calls += 1
        return self.fingerprint

    def get_best_available(self, ticker: str):
        self.read_calls += 1
        return [_row(2024), _row(2023), _row(2022)]


def _fundamentals(row: NormalizedFinancials) -> dict:
    """Row payload without the load timestamp.

    ``from_dict`` stamps ``loaded_at=now()`` when the serialized row has none,
    which only happens for hand-built rows; DB-backed rows always carry it and
    round-trip unchanged.
    """
    return {k: v for k, v in row.to_dict().items() if k != "loaded_at"}


def _cache(tmp_path, repo, version: str = ANALYSIS_VERSION, enabled: bool = True):
    return AnalysisCache(
        repository=repo, directory=tmp_path / "analysis", version=version, enabled=enabled
    )


# ----------------------------------------------------------------------
# cache semantics
# ----------------------------------------------------------------------


def test_hit_returns_identical_rows(tmp_path):
    repo = _Repo()
    cache = _cache(tmp_path, repo)
    rows = [_row(2024), _row(2023)]

    cache.put("AAPL", "fp-1", rows)
    got = cache.get("AAPL", "fp-1")

    assert got is not None
    assert [_fundamentals(r) for r in got] == [_fundamentals(r) for r in rows]
    assert cache.stats["hits"] == 1
    assert cache.stats["writes"] == 1


def test_fingerprint_change_invalidates(tmp_path):
    repo = _Repo()
    cache = _cache(tmp_path, repo)
    cache.put("AAPL", "fp-1", [_row(2024)])

    assert cache.get("AAPL", "fp-2") is None  # new filing arrived
    assert cache.get("AAPL", "fp-1") is not None  # old fingerprint still valid
    assert cache.stats["misses"] == 1


def test_version_bump_invalidates_everything(tmp_path):
    repo = _Repo()
    old = _cache(tmp_path, repo, version="1")
    old.put("AAPL", "fp-1", [_row(2024)])

    new = _cache(tmp_path, repo, version="2")
    assert new.get("AAPL", "fp-1") is None

    new.put("AAPL", "fp-1", [_row(2024, revenue=111.0)])
    assert _cache(tmp_path, repo, version="1").get("AAPL", "fp-1") is None
    assert new.get("AAPL", "fp-1")[0].revenue == 111.0


def test_missing_entry_and_disabled_cache(tmp_path):
    repo = _Repo()
    cache = _cache(tmp_path, repo)
    assert cache.get("MSFT", "fp-1") is None  # nothing stored

    off = _cache(tmp_path, repo, enabled=False)
    off.put("MSFT", "fp-1", [_row(2024)])
    assert not (tmp_path / "analysis" / "MSFT.json").exists()
    assert off.get("MSFT", "fp-1") is None
    assert off.fingerprint_for("MSFT") is None


def test_corrupt_entry_is_a_miss_not_a_crash(tmp_path):
    repo = _Repo()
    cache = _cache(tmp_path, repo)
    cache.put("AAPL", "fp-1", [_row(2024)])
    (tmp_path / "analysis" / "AAPL.json").write_text("{not json", encoding="utf-8")

    assert cache.get("AAPL", "fp-1") is None
    assert cache.stats["errors"] == 1


def test_write_is_atomic_and_no_temp_left(tmp_path):
    cache = _cache(tmp_path, _Repo())
    cache.put("AAPL", "fp-1", [_row(2024)])
    assert not list((tmp_path / "analysis").glob("*.tmp"))
    payload = json.loads((tmp_path / "analysis" / "AAPL.json").read_text())
    assert payload["fingerprint"] == "fp-1"
    assert payload["version"] == ANALYSIS_VERSION
    assert len(payload["rows"]) == 1


def test_invalidate_removes_entry(tmp_path):
    cache = _cache(tmp_path, _Repo())
    cache.put("AAPL", "fp-1", [_row(2024)])
    cache.invalidate("AAPL")
    assert cache.get("AAPL", "fp-1") is None


def test_no_repository_fingerprint_means_no_cache(tmp_path):
    """JSON/SQL repositories expose no fingerprint: the cache is a no-op."""
    cache = AnalysisCache(repository=object(), directory=tmp_path / "analysis")
    assert cache.enabled is True
    assert cache.fingerprint_for("AAPL") is None
    assert cache.get("AAPL", "fp-1") is None

    without_repo = AnalysisCache(repository=None, directory=tmp_path / "analysis")
    assert without_repo.enabled is False


def test_concurrent_writes_and_reads_are_consistent(tmp_path):
    cache = _cache(tmp_path, _Repo())
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for i in range(10):
                cache.put(f"T{n}", "fp-1", [_row(2020 + i)])
                cache.get(f"T{n}", "fp-1")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert not list((tmp_path / "analysis").glob("*.tmp"))


# ----------------------------------------------------------------------
# service integration
# ----------------------------------------------------------------------


class _Market:
    def get_market_cap(self, ticker):
        return 1_000.0

    def get_enterprise_value(self, ticker):
        return 1_200.0


def _service(repo, cache=None) -> CompanyAnalysisService:
    return CompanyAnalysisService(
        repository=repo, market_provider=_Market(), history_cache=cache
    )


def test_service_reuses_cached_history(tmp_path):
    repo = _Repo()
    cache = _cache(tmp_path, repo)
    service = _service(repo, cache)

    first = service._load_history("AAPL")
    second = service._load_history("AAPL")

    assert [_fundamentals(r) for r in first] == [_fundamentals(r) for r in second]
    # the second call never touched the repository (only the fingerprint probe)
    assert repo.read_calls == 1
    assert repo.fp_calls == 2
    assert cache.stats["hits"] == 1
    assert cache.stats["writes"] == 1


def test_service_rereads_when_fundamentals_change(tmp_path):
    repo = _Repo()
    cache = _cache(tmp_path, repo)
    service = _service(repo, cache)

    service._load_history("AAPL")
    repo.fingerprint = "fp-2"  # a new filing landed
    service._load_history("AAPL")

    assert repo.read_calls == 2
    assert cache.stats["writes"] == 2


def test_service_without_cache_reads_every_time(tmp_path):
    repo = _Repo()
    service = _service(repo, None)

    service._load_history("AAPL")
    service._load_history("AAPL")

    assert repo.read_calls >= 2
    assert not (tmp_path / "analysis").exists()
