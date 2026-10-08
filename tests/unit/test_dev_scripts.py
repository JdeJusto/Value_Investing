"""Static guards for the developer helper scripts.

These are not integration tests: they only assert that the scripts the docs
tell the user to run actually exist, are executable, and declare a bash
shebang. The scripts themselves need a desktop session (emulator window),
so they cannot run in CI.
"""

from __future__ import annotations

import stat
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dev_emulator.sh"


def test_dev_emulator_script_exists_and_is_executable():
    assert SCRIPT.exists(), "dev_emulator.sh must exist"
    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, "dev_emulator.sh must be executable"


def test_dev_emulator_script_has_bash_shebang():
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
