"""Recompute the passed-test count badge in the README files.

Usage::

    python -m scripts.update_badges          # update in place
    python -m scripts.update_badges --check  # exit 1 if stale

The count is taken from a real unit-suite run (``N passed``), not
``--collect-only``: collected tests can include tests that are skipped, so
labeling the collected count as "passed" would be inaccurate.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_FILES = ("README.md", "README.es.md")
TEST_COUNT_RE = re.compile(r"\b(\d+)\s+passed\b", re.IGNORECASE)
TEST_BADGE_RE = re.compile(r"(tests-)(\d+)(%20passed)")
TEST_ALT_RE = re.compile(r'(alt=")[\d,]+( tests? passed")', re.IGNORECASE)


class BadgeError(RuntimeError):
    """The test suite or badge text could not be read reliably."""


def parse_passed_count(output: str) -> int:
    """Return the final ``N passed`` count from pytest's output."""
    matches = TEST_COUNT_RE.findall(output)
    if not matches:
        raise BadgeError("could not find a 'N passed' summary in pytest output")
    return int(matches[-1])


def collect_test_count(root: Path = ROOT) -> int:
    """Run the unit suite and return its passed-test count."""
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/unit",
        "-q",
        "--no-header",
    ]
    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        raise BadgeError(
            "pytest tests/unit failed; refusing to update the test badge\n"
            + output[-4000:]
        )
    return parse_passed_count(output)


def update_badge_text(text: str, count: int) -> tuple[str, int]:
    """Replace badge URL and alt-text counts; return new text and matches changed."""
    updated, changed = TEST_BADGE_RE.subn(rf"\g<1>{count}\g<3>", text)
    updated, alt_changed = TEST_ALT_RE.subn(
        lambda match: f"{match.group(1)}{count:,}{match.group(2)}", updated
    )
    return updated, changed + alt_changed


def update_readmes(
    root: Path, count: int, *, check: bool = False
) -> tuple[int, list[str]]:
    """Update/check root README badges and the optional Spanish README.

    Returns ``(exit_code, messages)``. The English README badge is required;
    README.es.md is updated only if it exists and contains the same badge form.
    """
    mismatches = 0
    messages: list[str] = []
    for filename in README_FILES:
        path = root / filename
        if not path.exists():
            if filename == "README.md":
                raise BadgeError(f"required file not found: {path}")
            continue

        original = path.read_text(encoding="utf-8")
        updated, replacements = update_badge_text(original, count)
        if replacements == 0:
            if filename == "README.md":
                raise BadgeError(f"test-count badge not found in {path}")
            messages.append(f"{filename}: no test-count badge; skipped")
            continue

        existing_counts = [
            int(value) for value in re.findall(r"tests-(\d+)%20passed", original)
        ]
        is_stale = updated != original
        if is_stale:
            mismatches += 1
            messages.append(
                f"{filename}: badge count {', '.join(map(str, existing_counts))}; "
                f"expected {count} passed"
            )
        else:
            messages.append(f"{filename}: test badge is current ({count} passed)")

        if not check and is_stale:
            path.write_text(updated, encoding="utf-8")
            messages.append(f"{filename}: updated")

    return (1 if check and mismatches else 0), messages


def main(argv: list[str] | None = None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any test-count badge is stale; do not write files",
    )
    args = parser.parse_args(argv)

    try:
        count = collect_test_count(root)
        exit_code, messages = update_readmes(root, count, check=args.check)
    except BadgeError as exc:
        print(f"update_badges: {exc}", file=sys.stderr)
        return 1

    print(f"Unit tests: {count} passed")
    for message in messages:
        print(message)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
