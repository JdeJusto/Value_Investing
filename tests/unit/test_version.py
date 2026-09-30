"""The package version must match the latest CHANGELOG release."""

from __future__ import annotations

import re
from pathlib import Path

from backend import __version__

CHANGELOG = Path(__file__).resolve().parents[2] / "CHANGELOG.md"


def test_version_matches_latest_changelog_entry():
    text = CHANGELOG.read_text(encoding="utf-8")
    releases = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", text, flags=re.MULTILINE)
    assert releases, "CHANGELOG.md has no release entries"
    assert releases[0] == __version__
