"""Write-lock invariant tests for :class:`PortfolioService`.

The service must run every read-modify-write cycle inside an exclusive
``fcntl.flock`` so concurrent writers (API, CLI, Streamlit) never lose an
update. The concurrency test widens the read window with a slow loader: the
old unlocked code lost one of the two adds, the locked code keeps both.
"""

from __future__ import annotations

import fcntl
import threading
import time

from backend.portfolio.portfolio_repository import JsonPortfolioRepository
from backend.portfolio.portfolio_service import PortfolioService


def _spy_flock(monkeypatch) -> list[int]:
    """Record flock operations without taking the real lock."""
    calls: list[int] = []

    def fake_flock(fd, op):
        calls.append(op)

    monkeypatch.setattr(fcntl, "flock", fake_flock)
    return calls


def _fresh_service(tmp_path) -> tuple[PortfolioService, JsonPortfolioRepository]:
    repository = JsonPortfolioRepository(tmp_path / "portfolio.json")
    return PortfolioService(repository), repository


def test_add_acquires_the_exclusive_lock(tmp_path, monkeypatch):
    calls = _spy_flock(monkeypatch)
    service, _ = _fresh_service(tmp_path)
    service.add("AAPL", 10.0, 150.0)
    assert fcntl.LOCK_EX in calls
    assert fcntl.LOCK_UN in calls


def test_exit_and_remove_acquire_the_lock(tmp_path, monkeypatch):
    calls = _spy_flock(monkeypatch)
    service, _ = _fresh_service(tmp_path)
    service.add("AAPL", 10.0, 150.0)
    calls.clear()
    assert service.exit("AAPL", 160.0) is not None
    assert fcntl.LOCK_EX in calls
    calls.clear()
    assert service.remove("AAPL") is not None
    assert fcntl.LOCK_EX in calls


def test_save_prices_goes_through_the_lock(tmp_path, monkeypatch):
    service, repository = _fresh_service(tmp_path)
    service.add("AAPL", 10.0, 150.0)
    calls = _spy_flock(monkeypatch)
    updated = service.save_prices({"AAPL": 175.0, "ZZZZ": 9.0, "KO": -3.0})
    assert updated == 1
    assert fcntl.LOCK_EX in calls
    assert repository.load().position("AAPL").current_price == 175.0


def test_view_and_performance_use_the_lock(tmp_path, monkeypatch):
    service, _ = _fresh_service(tmp_path)
    service.add("AAPL", 10.0, 150.0)
    calls = _spy_flock(monkeypatch)
    service.view()
    assert fcntl.LOCK_EX in calls
    calls.clear()
    service.performance()
    assert fcntl.LOCK_EX in calls


def test_lock_file_lives_next_to_the_portfolio_json(tmp_path):
    service, _ = _fresh_service(tmp_path)
    service.add("AAPL", 10.0, 150.0)
    assert (tmp_path / "portfolio.json.lock").exists()


def test_concurrent_adds_do_not_lose_updates(tmp_path, monkeypatch):
    """Two threads adding at once: both positions survive."""
    service, repository = _fresh_service(tmp_path)
    original_load = service._load

    def slow_load():
        # Widen the read window: without the lock both threads would load the
        # empty file, then the second save would drop the first position.
        time.sleep(0.05)
        return original_load()

    monkeypatch.setattr(service, "_load", slow_load)
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def worker(ticker: str) -> None:
        try:
            barrier.wait(timeout=5)
            service.add(ticker, 1.0, 100.0)
        except Exception as exc:  # noqa: BLE001 — collected, then asserted
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(ticker,)) for ticker in ("AAA", "BBB")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    stored = repository.load()
    assert {p.ticker for p in stored.positions} == {"AAA", "BBB"}
    assert stored.position("AAA").quantity == 1.0
    assert stored.position("BBB").quantity == 1.0


def test_many_concurrent_workers_keep_every_position(tmp_path):
    """Eight simultaneous adds over the real lock: nothing is lost."""
    service, repository = _fresh_service(tmp_path)
    tickers = [f"T{i}" for i in range(8)]
    barrier = threading.Barrier(len(tickers))
    errors: list[Exception] = []

    def worker(ticker: str) -> None:
        try:
            barrier.wait(timeout=5)
            service.add(ticker, 2.0, 50.0)
        except Exception as exc:  # noqa: BLE001 — collected, then asserted
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in tickers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert errors == []
    stored = repository.load()
    assert {p.ticker for p in stored.positions} == set(tickers)


def test_save_prices_does_not_clobber_a_concurrent_add(tmp_path, monkeypatch):
    """A price save racing an add must not drop either change."""
    service, repository = _fresh_service(tmp_path)
    service.add("AAPL", 10.0, 150.0)
    original_load = service._load

    def slow_load():
        time.sleep(0.05)
        return original_load()

    monkeypatch.setattr(service, "_load", slow_load)
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def saver() -> None:
        try:
            barrier.wait(timeout=5)
            service.save_prices({"AAPL": 175.0})
        except Exception as exc:  # noqa: BLE001 — collected, then asserted
            errors.append(exc)

    def adder() -> None:
        try:
            barrier.wait(timeout=5)
            service.add("KO", 1.0, 50.0)
        except Exception as exc:  # noqa: BLE001 — collected, then asserted
            errors.append(exc)

    threads = [threading.Thread(target=saver), threading.Thread(target=adder)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    stored = repository.load()
    assert stored.position("AAPL").current_price == 175.0
    assert stored.position("KO") is not None
