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
    "soupsieve": (2, "see docs/backlog.md § Pipenv lock exceptions"),
    "websockets": (16, "see docs/backlog.md § Pipenv lock exceptions"),
    "fastapi": (0, "see docs/backlog.md § Pipenv lock exceptions"),  # 0.150.x
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
    # fastapi special case: 0.150.x vs 0.151.x differ in minor, not major
    if pkg == "fastapi":
        minor = int(version.split(".")[1])
        assert minor <= 150, (
            f"{pkg} is {version}, exceeds 0.150.x ({reason}). If the bump is "
            f"intentional, update this test AND docs/backlog.md in the same "
            f"commit."
        )
    else:
        assert major <= max_major, (
            f"{pkg} is {version}, exceeds major {max_major} ({reason}). If the "
            f"bump is intentional, update this test AND docs/backlog.md in the "
            f"same commit."
        )
