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
        check=False,
    )
    assert result.returncode == 0
    assert "DEBUG" not in result.stderr
    assert "DEBUG" not in result.stdout
    assert "usage: main.py" in result.stdout


def test_no_debug_prints_left_in_cli_sources():
    """``--help`` cannot catch debug noise printed while a command runs, so
    the CLI sources are scanned directly (``historical-valuation`` shipped
    three of them on stderr)."""
    offenders = []
    for path in sorted((PROJECT_ROOT / "cli").rglob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if line.strip().startswith("print(") and "DEBUG" in line:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno}")
    assert offenders == []
