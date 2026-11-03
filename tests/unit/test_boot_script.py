"""Tests for the boot-triggered daily workflow wrapper.

The static checks pin the wrapper's contract (per-day stamp, lock, network
wait, `--resume`, non-fatal validation, no sudo) and the functional test runs
the real bash script against a fake interpreter, so nothing here starts the
actual workflow or touches a database.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_daily_on_boot.sh"
UNIT = ROOT / "deploy" / "systemd" / "value-investing-daily-boot.service"


def test_boot_script_exists_and_is_executable():
    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK)


def test_boot_script_has_a_shebang_and_strict_mode():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text


def test_boot_script_guards_on_a_per_day_stamp():
    text = SCRIPT.read_text(encoding="utf-8")
    assert ".last_daily_run" in text
    assert "date +%Y-%m-%d" in text
    assert "--force" in text


def test_boot_script_uses_a_lock_and_resumes():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "flock" in text
    assert "--resume" in text
    assert "scripts.daily_workflow" in text


def test_boot_script_waits_for_the_network():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "VI_NETWORK_TIMEOUT_SECONDS" in text
    assert "data.sec.gov" in text


def test_boot_script_runs_the_validation_without_failing_the_run():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "scripts.validate_data_sample" in text
    # The validation is best-effort: a non-zero exit is logged, not fatal.
    assert 'if ! "$PYTHON" -m scripts.validate_data_sample' in text


def test_boot_script_regenerates_peer_stats_on_a_weekly_day():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "scripts.build_peer_stats" in text
    assert "date +%u" in text  # ISO weekday gate
    assert "VI_PEER_STATS_DAY" in text
    # Never fatal: the peer build must not change the workflow's exit status.
    assert "PEER_STATUS" in text
    assert 'exit "$WORKFLOW_STATUS"' in text


def test_boot_script_never_uses_sudo():
    assert _never_invokes_sudo(SCRIPT)


def test_boot_script_runs_the_monthly_audit_in_the_first_week():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "scripts.audit_data_quality" in text
    assert "VI_AUDIT_SAMPLE" in text
    assert "VI_AUDIT_WEEKDAY" in text
    assert "VI_AUDIT_FIRST_DAY_MAX" in text
    assert "date +%d" in text  # the "first week of the month" gate
    # A finding (exit 1) is news for the log, never a failure of the day.
    assert "AUDIT_STATUS" in text
    assert 'exit "$WORKFLOW_STATUS"' in text


def test_boot_script_passes_bash_syntax_check():
    if shutil.which("bash") is None:  # pragma: no cover - bash is required to run it
        pytest.skip("bash not available")
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True, capture_output=True)


def _no_sudo_invocation(path: Path) -> bool:
    """True when no non-comment line in the file invokes sudo."""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "sudo" in stripped:
            return False
    return True


def test_systemd_unit_matches_the_wrapper():
    text = UNIT.read_text(encoding="utf-8")
    assert "Type=oneshot" in text
    assert "ExecStart=%h/Value_Investing/scripts/run_daily_on_boot.sh" in text
    assert "WantedBy=default.target" in text
    assert _never_invokes_sudo(UNIT)


def _never_invokes_sudo(path: Path) -> bool:
    """True when no executable (non-comment) line invokes sudo."""
    return not any(
        line.strip().startswith("sudo") or "| sudo " in line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    )


# ---------------------------------------------------------------------------
# functional: run the real script against a fake interpreter
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_python(tmp_path: Path) -> tuple[Path, Path]:
    """A stand-in for the venv python that records its argv and exits 0.

    ``FAKE_PYTHON_FAIL_ON`` (an argv fragment) makes it exit 1 instead, so a
    test can prove one step's failure never fails the whole run.
    """
    calls = tmp_path / "calls.log"
    interpreter = tmp_path / "fake_python.sh"
    interpreter.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> "$FAKE_PYTHON_CALLS"\n'
        'if [[ -n "${FAKE_PYTHON_FAIL_ON:-}" && "$*" == *"$FAKE_PYTHON_FAIL_ON"* ]]; then\n'
        "    exit 1\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    interpreter.chmod(0o755)
    return interpreter, calls


def _run(
    tmp_path: Path,
    fake_python: tuple[Path, Path],
    *args: str,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    interpreter, calls = fake_python
    env = os.environ | {
        "VI_PYTHON": str(interpreter),
        "VI_LOGS_DIR": str(tmp_path / "logs"),
        "VI_SKIP_NETWORK_WAIT": "1",
        "VI_WORKFLOW_EXTRA_ARGS": "--dry-run --limit 2",
        "FAKE_PYTHON_CALLS": str(calls),
    }
    env.update(env_extra or {})
    return subprocess.run(
        [str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_boot_script_runs_and_stamps_the_day(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover - util-linux is standard
        pytest.skip("flock not available")
    _, calls = fake_python

    result = _run(tmp_path, fake_python)
    assert result.returncode == 0, result.stderr

    calls_text = calls.read_text(encoding="utf-8")
    assert "scripts.daily_workflow" in calls_text
    assert "--resume" in calls_text
    assert "--dry-run --limit 2" in calls_text
    assert "scripts.validate_data_sample --sample 10 --out" in calls_text

    today = datetime.now(UTC).astimezone().date().isoformat()
    stamp = (tmp_path / "logs" / ".last_daily_run").read_text(encoding="utf-8").strip()
    assert stamp == today


def test_boot_script_is_a_noop_when_already_ran_today(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    assert _run(tmp_path, fake_python).returncode == 0
    first = calls.read_text(encoding="utf-8")

    second = _run(tmp_path, fake_python)
    assert first == calls.read_text(encoding="utf-8")
    assert "already ran today" in first or first != ""
    assert "nothing to do" in (tmp_path / "logs" / f"run_{_today()}.log").read_text(
        encoding="utf-8"
    )
    assert second.returncode == 0


def test_boot_script_force_reruns(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    assert _run(tmp_path, fake_python).returncode == 0
    before = calls.read_text(encoding="utf-8").count("scripts.daily_workflow")
    assert _run(tmp_path, fake_python, "--force").returncode == 0
    after = calls.read_text(encoding="utf-8")
    assert after.count("scripts.daily_workflow") > before


def test_boot_script_rejects_unknown_arguments(tmp_path, fake_python):
    result = _run(tmp_path, fake_python, "--nonsense")
    assert result.returncode == 2


def _today() -> str:
    return datetime.now(UTC).astimezone().date().isoformat()


def test_boot_script_rebuilds_peer_stats_on_the_weekly_day(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    day = _local_isoweekday()
    result = _run(tmp_path, fake_python, env_extra={"VI_PEER_STATS_DAY": str(day)})
    assert result.returncode == 0, result.stderr
    assert "scripts.build_peer_stats" in calls.read_text(encoding="utf-8")


def test_boot_script_skips_peer_stats_on_other_days(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    other = _local_isoweekday() % 7 + 1  # any other ISO weekday
    result = _run(tmp_path, fake_python, env_extra={"VI_PEER_STATS_DAY": str(other)})
    assert result.returncode == 0, result.stderr
    assert "scripts.build_peer_stats" not in calls.read_text(encoding="utf-8")


def test_boot_script_peer_stats_can_be_disabled(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    result = _run(tmp_path, fake_python, env_extra={"VI_PEER_STATS_DAY": "0"})
    assert result.returncode == 0, result.stderr
    assert "scripts.build_peer_stats" not in calls.read_text(encoding="utf-8")


def test_boot_script_peer_stats_defaults_to_sunday(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    result = _run(tmp_path, fake_python)
    assert result.returncode == 0, result.stderr
    ran = "scripts.build_peer_stats" in calls.read_text(encoding="utf-8")
    assert ran is (_local_isoweekday() == 7)


def test_boot_script_accepts_extra_peer_stats_args(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    result = _run(
        tmp_path,
        fake_python,
        env_extra={
            "VI_PEER_STATS_DAY": str(_local_isoweekday()),
            "VI_PEER_STATS_EXTRA_ARGS": "--limit 25 --no-prices",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "scripts.build_peer_stats --limit 25 --no-prices" in calls.read_text(
        encoding="utf-8"
    )


def test_boot_script_peer_stats_failure_is_not_fatal(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    result = _run(
        tmp_path,
        fake_python,
        env_extra={
            "VI_PEER_STATS_DAY": str(_local_isoweekday()),
            "FAKE_PYTHON_FAIL_ON": "build_peer_stats",
        },
    )
    assert result.returncode == 0, result.stderr
    text = calls.read_text(encoding="utf-8")
    assert "scripts.build_peer_stats" in text
    # The workflow ran first and kept its own (successful) status.
    assert text.index("scripts.daily_workflow") < text.index("scripts.build_peer_stats")
    run_log = (tmp_path / "logs" / f"run_{_today()}.log").read_text(encoding="utf-8")
    assert "peer statistics finished with status 1" in run_log


def _local_isoweekday() -> int:
    return datetime.now(UTC).astimezone().isoweekday()


def _today_day() -> int:
    return datetime.now(UTC).astimezone().day


def test_boot_script_runs_the_audit_in_the_first_week(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    result = _run(
        tmp_path,
        fake_python,
        env_extra={
            "VI_AUDIT_WEEKDAY": str(_local_isoweekday()),
            "VI_AUDIT_FIRST_DAY_MAX": "31",
        },
    )
    assert result.returncode == 0, result.stderr
    assert (
        "scripts.audit_data_quality --sample 30 --sources sec,yahoo"
        in calls.read_text(encoding="utf-8")
    )


def test_boot_script_skips_the_audit_after_the_first_week(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    result = _run(
        tmp_path,
        fake_python,
        env_extra={
            "VI_AUDIT_WEEKDAY": str(_local_isoweekday()),
            # Below today's day of month, so the "first week" gate is shut.
            "VI_AUDIT_FIRST_DAY_MAX": str(_today_day() - 1),
        },
    )
    assert result.returncode == 0, result.stderr
    assert "scripts.audit_data_quality" not in calls.read_text(encoding="utf-8")


def test_boot_script_skips_the_audit_on_other_weekdays(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    result = _run(
        tmp_path,
        fake_python,
        env_extra={
            "VI_AUDIT_WEEKDAY": str(_local_isoweekday() % 7 + 1),
            "VI_AUDIT_FIRST_DAY_MAX": "31",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "scripts.audit_data_quality" not in calls.read_text(encoding="utf-8")


def test_boot_script_can_disable_the_audit(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    result = _run(
        tmp_path,
        fake_python,
        env_extra={
            "VI_AUDIT_SAMPLE": "0",
            "VI_AUDIT_WEEKDAY": str(_local_isoweekday()),
            "VI_AUDIT_FIRST_DAY_MAX": "31",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "scripts.audit_data_quality" not in calls.read_text(encoding="utf-8")


def test_boot_script_audit_defaults_to_the_first_sunday(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    result = _run(tmp_path, fake_python)
    assert result.returncode == 0, result.stderr
    ran = "scripts.audit_data_quality" in calls.read_text(encoding="utf-8")
    assert ran is (_local_isoweekday() == 7 and _today_day() <= 7)


def test_boot_script_accepts_extra_audit_args(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")
    _, calls = fake_python

    result = _run(
        tmp_path,
        fake_python,
        env_extra={
            "VI_AUDIT_WEEKDAY": str(_local_isoweekday()),
            "VI_AUDIT_FIRST_DAY_MAX": "31",
            "VI_AUDIT_EXTRA_ARGS": "--sample 3",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "--sample 3" in calls.read_text(encoding="utf-8")


def test_boot_script_audit_finding_is_not_fatal(tmp_path, fake_python):
    if shutil.which("flock") is None:  # pragma: no cover
        pytest.skip("flock not available")

    result = _run(
        tmp_path,
        fake_python,
        env_extra={
            "VI_AUDIT_WEEKDAY": str(_local_isoweekday()),
            "VI_AUDIT_FIRST_DAY_MAX": "31",
            "FAKE_PYTHON_FAIL_ON": "audit_data_quality",
        },
    )
    assert result.returncode == 0, result.stderr
    run_log = (tmp_path / "logs" / f"run_{_today()}.log").read_text(encoding="utf-8")
    assert "data-quality audit finished with status 1" in run_log
