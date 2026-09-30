"""Regression: the CLI entry points print no DEBUG noise on stderr.

``main.py`` and ``cli/main.py`` shipped leftover debug prints; this test
fails if any come back.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_help_has_no_debug_output():
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    assert "DEBUG" not in result.stderr
    assert "DEBUG" not in result.stdout
    assert "usage: main.py" in result.stdout
