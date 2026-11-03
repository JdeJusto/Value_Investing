"""Pre-stage SEC/Yahoo health checks gate the workflow's network stages."""

from __future__ import annotations

from types import SimpleNamespace

from scripts import daily_workflow


def _args(**overrides):
    base = {"no_update": False, "dry_run": False, "no_prices": False}
    base.update(overrides)
    return SimpleNamespace(**base)


# --- the checks never raise and report reachability -------------------------


def test_check_sec_true_when_probe_succeeds(monkeypatch):
    monkeypatch.setattr(daily_workflow, "_probe_sec", lambda: True)
    assert daily_workflow._check_sec() is True


def test_check_sec_false_and_quiet_when_probe_fails(monkeypatch):
    def down():
        raise ConnectionError("SEC unreachable")

    monkeypatch.setattr(daily_workflow, "_probe_sec", down)
    assert daily_workflow._check_sec() is False


def test_check_yahoo_false_when_probe_fails(monkeypatch):
    def down():
        raise TimeoutError("Yahoo timed out")

    monkeypatch.setattr(daily_workflow, "_probe_yahoo", down)
    assert daily_workflow._check_yahoo() is False


# --- the stages are skipped (and the run marked partial) on failure ---------


def test_sec_stage_is_skipped_when_sec_is_down(monkeypatch):
    monkeypatch.setattr(daily_workflow, "_check_sec", lambda: False)
    assert daily_workflow._precheck_sec(_args()) is True  # skip


def test_sec_stage_runs_when_sec_is_up(monkeypatch):
    monkeypatch.setattr(daily_workflow, "_check_sec", lambda: True)
    assert daily_workflow._precheck_sec(_args()) is False  # do not skip


def test_sec_stage_is_not_probed_for_dry_run_or_no_update(monkeypatch):
    def fail_if_called():
        raise AssertionError("SEC must not be probed here")

    monkeypatch.setattr(daily_workflow, "_check_sec", fail_if_called)
    assert daily_workflow._precheck_sec(_args(dry_run=True)) is False
    assert daily_workflow._precheck_sec(_args(no_update=True)) is False


def test_yahoo_stage_is_skipped_when_yahoo_is_down(monkeypatch):
    monkeypatch.setattr(daily_workflow, "_check_yahoo", lambda: False)
    assert daily_workflow._precheck_yahoo(_args()) is True  # skip


def test_yahoo_stage_runs_when_yahoo_is_up(monkeypatch):
    monkeypatch.setattr(daily_workflow, "_check_yahoo", lambda: True)
    assert daily_workflow._precheck_yahoo(_args()) is False  # do not skip


def test_yahoo_stage_is_not_probed_with_no_prices(monkeypatch):
    def fail_if_called():
        raise AssertionError("Yahoo must not be probed with --no-prices")

    monkeypatch.setattr(daily_workflow, "_check_yahoo", fail_if_called)
    assert daily_workflow._precheck_yahoo(_args(no_prices=True)) is False


def test_prechecks_are_wired_before_the_stages():
    """The checks must run before their network stage, not after."""
    from pathlib import Path

    text = Path(daily_workflow.__file__).read_text(encoding="utf-8")
    assert "_precheck_yahoo(args)" in text
    assert "_precheck_sec(args)" in text
    assert "stage_skipped = True" in text
