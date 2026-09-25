"""Unit tests for the daily-workflow run state (resume checkpoint)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from backend.services.run_state import (
    RUN_STATE_FILENAME,
    RunState,
    archive_path,
    is_transient_failure,
    new_run_id,
    options_fingerprint,
)


class _Args:
    universe = "sp500"
    limit = 20
    max_refresh = 200
    top = 20
    no_prices = False
    no_update = False
    refresh = False
    no_refresh = False
    freshness_hours = None


def _create(out: Path, total: int = 20) -> RunState:
    return RunState.create(
        out / RUN_STATE_FILENAME,
        universe_spec="sp500",
        options=options_fingerprint(_Args()),
        total_tickers=total,
    )


def test_new_run_id_is_sortable_and_unique():
    a = new_run_id()
    b = new_run_id()
    assert a[:20].endswith("Z")  # ...T%H:%M:%SZ-xxxxxx
    assert len(a.split("-")[-1]) == 6
    assert a != b
    assert a[0:4].isdigit()


def test_transient_failure_classification():
    for reason in (
        "SEC sync timed out after 300s",
        "HTTP 403 rate limit",
        "connection reset by peer",
        "SEC unreachable: Name or service not known",
    ):
        assert is_transient_failure(reason), reason
    for reason in (
        "no CIK mapping in Financial-DataBase",
        "analysis returned no data",
        "Validation failed: bad unit",
    ):
        assert not is_transient_failure(reason), reason


def test_create_writes_structure_and_no_temp_left(tmp_path):
    state = _create(tmp_path)
    path = tmp_path / RUN_STATE_FILENAME
    assert path.exists()
    assert not list(tmp_path.glob("*.tmp"))
    payload = json.loads(path.read_text())
    assert payload["run_id"] == state.run_id
    assert payload["universe"] == "sp500"
    assert payload["total_tickers"] == 20
    assert payload["completed"] == []
    assert payload["current_stage"] == "refresh"
    assert payload["stage_progress"] == {"refresh": 0, "prices": 0, "analysis": 0}
    assert payload["prices_fetched"] == 0
    assert payload["alerts_generated"] == 0
    assert payload["options"]["max_refresh"] == 200


def test_load_roundtrip_and_matches(tmp_path):
    state = _create(tmp_path)
    state.add_completed("AAPL")
    state.set_stage("analysis")

    loaded = RunState.load(tmp_path / RUN_STATE_FILENAME)
    assert loaded is not None
    assert loaded.run_id == state.run_id
    assert loaded.completed == ["AAPL"]
    assert loaded.current_stage == "analysis"
    assert loaded.matches(universe_spec="sp500", options=options_fingerprint(_Args()))
    assert not loaded.matches(
        universe_spec="nasdaq100", options=options_fingerprint(_Args())
    )


def test_corrupt_state_is_ignored(tmp_path):
    path = tmp_path / RUN_STATE_FILENAME
    path.write_text("{not json", encoding="utf-8")
    assert RunState.load(path) is None


def test_completed_is_deduplicated_and_removes_skip(tmp_path):
    state = _create(tmp_path)
    state.add_skipped("AAPL", "resume: completed in previous run")
    state.add_completed("AAPL")
    state.add_completed("AAPL")
    assert state.completed == ["AAPL"]
    assert "AAPL" not in state.skipped


def test_failed_transient_and_permanent_sets(tmp_path):
    state = _create(tmp_path)
    state.add_failed("AAPL", "SEC sync timed out after 300s")
    state.add_failed("BADX", "no CIK mapping in Financial-DataBase")
    assert state.transient_failures() == {"AAPL"}
    assert state.permanent_failures() == {"BADX"}


def test_progress_counters_and_stage(tmp_path):
    state = _create(tmp_path)
    state.note_progress("refresh", "A")
    state.note_progress("refresh", "B")
    state.note_progress("analysis", "A")
    state.set_prices_fetched(7)
    state.set_alerts_generated(2)
    state.set_stage("report")

    loaded = RunState.load(tmp_path / RUN_STATE_FILENAME)
    assert loaded.stage_progress == {"refresh": 2, "prices": 0, "analysis": 1}
    assert loaded.prices_fetched == 7
    assert loaded.alerts_generated == 2
    assert loaded.current_stage == "report"


def test_archive_moves_file_and_find_retrieves_it(tmp_path):
    state = _create(tmp_path)
    state.add_completed("MSFT")
    run_id = state.run_id

    archived = state.archive()
    assert archived == archive_path(tmp_path, run_id)
    assert archived.exists()
    assert not (tmp_path / RUN_STATE_FILENAME).exists()

    found = RunState.find(tmp_path, run_id)
    assert found is not None
    assert found.run_id == run_id
    assert found.completed == ["MSFT"]
    assert RunState.find(tmp_path, "2020-01-01T00:00:00Z-000000") is None


def test_complete_archives_and_marks_done(tmp_path):
    state = _create(tmp_path)
    target = state.complete()
    assert target.exists()
    assert not (tmp_path / RUN_STATE_FILENAME).exists()
    payload = json.loads(target.read_text())
    assert payload["current_stage"] == "done"
    assert "finished_at" in payload


def test_find_prefers_live_file(tmp_path):
    state = _create(tmp_path)
    found = RunState.find(tmp_path, state.run_id)
    assert found is not None
    assert found.path == tmp_path / RUN_STATE_FILENAME


def test_concurrent_completions_are_all_recorded(tmp_path):
    state = _create(tmp_path)

    def worker(prefix: str) -> None:
        for i in range(25):
            state.add_completed(f"{prefix}{i}")

    threads = [threading.Thread(target=worker, args=(p,)) for p in ("A", "B", "C")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    loaded = RunState.load(tmp_path / RUN_STATE_FILENAME)
    assert len(loaded.completed) == 75
    assert len(set(loaded.completed)) == 75
