"""Contract tests for the Pipfile.lock pin exceptions.

Phase C of the v0.19 cycle reverted 4 major-version bumps manually because
regenerating the lock from scratch reintroduced them. These pins are
intentional; see docs/backlog.md § "Pipenv lock exceptions".

If this test fails, either:
  (a) Someone regenerated Pipfile.lock without filtering the exceptions, or
  (b) The exceptions are no longer needed and this test should be updated
      (deliberately, in its own commit).
"""

import json
from pathlib import Path

import pytest

LOCK = Path(__file__).resolve().parents[2] / "Pipfile.lock"

# Pinned exceptions: package -> (max_major, reason)
# major_version = int(version.split(".")[0])
PINNED_MAJOR = {
    "pyarrow": (25, "see docs/backlog.md § Pipenv lock exceptions"),
    "soupsieve": (4, "security upgrade to 4.0.0 (2026-11-13); see docs/backlog.md"),
    "websockets": (16, "see docs/backlog.md § Pipenv lock exceptions"),
}


@pytest.mark.parametrize(
    "pkg,max_major,reason",
    [(pkg, max_major, reason) for pkg, (max_major, reason) in PINNED_MAJOR.items()],
)
def test_pinned_major_not_exceeded(pkg: str, max_major: int, reason: str) -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    entry = lock["default"].get(pkg) or lock["develop"].get(pkg)
    if entry is None:
        pytest.skip(f"{pkg} not in lock (was it removed?)")
    version = entry["version"].lstrip("=")
    major = int(version.split(".")[0])
    assert major <= max_major, (
        f"{pkg} is {version}, exceeds major {max_major} ({reason}). If the "
        f"bump is intentional, update this test AND docs/backlog.md in the "
        f"same commit."
    )
