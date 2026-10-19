"""The workflow returns meaningful exit codes and the boot wrapper keeps them."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts import daily_workflow

ROOT = Path(daily_workflow.__file__).resolve().parents[1]


def test_exit_code_constants():
    assert daily_workflow.EXIT_OK == 0
    assert daily_workflow.EXIT_PARTIAL == 1
    assert daily_workflow.EXIT_FAILED == 2


@pytest.mark.parametrize(
    ("stage_skipped", "expected"),
    [(False, daily_workflow.EXIT_OK), (True, daily_workflow.EXIT_PARTIAL)],
)
def test_exit_code_mapping(stage_skipped, expected):
    assert daily_workflow._exit_code(stage_skipped) == expected


def _patch_main(monkeypatch, run):
    monkeypatch.setattr(sys, "argv", ["daily_workflow.py"])
    monkeypatch.setattr(daily_workflow, "_configure_logging", lambda _verbose: None)
    monkeypatch.setattr(daily_workflow, "_run", run)


def test_main_returns_the_run_code(monkeypatch):
    _patch_main(monkeypatch, lambda _args: daily_workflow.EXIT_PARTIAL)
    assert daily_workflow.main() == daily_workflow.EXIT_PARTIAL


def test_main_maps_a_startup_crash_to_failed(monkeypatch):
    def boom(_args):
        raise RuntimeError("database unreachable")

    _patch_main(monkeypatch, boom)
    assert daily_workflow.main() == daily_workflow.EXIT_FAILED


def test_main_returns_130_on_keyboard_interrupt(monkeypatch):
    def interrupt(_args):
        raise KeyboardInterrupt

    _patch_main(monkeypatch, interrupt)
    assert daily_workflow.main() == 130


def test_main_propagates_system_exit(monkeypatch):
    """Config/argparse errors keep their own code (not rewritten to 2)."""

    def bad_config(_args):
        raise SystemExit(3)

    _patch_main(monkeypatch, bad_config)
    with pytest.raises(SystemExit) as excinfo:
        daily_workflow.main()
    assert excinfo.value.code == 3


def test_boot_script_propagates_the_workflow_exit_code():
    text = (ROOT / "scripts" / "run_daily_on_boot.sh").read_text(encoding="utf-8")
    assert 'exit "$WORKFLOW_STATUS"' in text
    # Never masked by a `|| true`.
    assert "|| true" not in text
    # The best-effort steps keep their own statuses and never touch the code.
    assert "PEER_STATUS" in text
    assert "AUDIT_STATUS" in text
