"""Fail on npm high/critical vulnerabilities, except explicit accepted GHSAs.

`npm audit --audit-level=high` fails the whole CI job when a transitive
advisory has no patched version (e.g. picomatch GHSA-fc5q-39xc-vjpf on
2026-11-18). This gate keeps the high/critical bar but allows a small,
reviewed allowlist of advisory IDs. Critical findings are never allowed.

Usage:
    python scripts/npm_audit_gate.py --cwd mobile
    python scripts/npm_audit_gate.py --cwd frontend
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_ALLOWLIST = (
    Path(__file__).resolve().parents[1] / "config" / "npm_audit_allowlist.txt"
)


def load_allowlist(path: Path) -> set[str]:
    """Read one GHSA id per line; ``#`` starts a comment."""
    allowed: set[str] = set()
    if not path.exists():
        return allowed
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].strip()
        if token:
            allowed.add(token)
    return allowed


def _dict_advisory_ids(via: list) -> set[str] | None:
    ids: set[str] = set()
    for item in via or []:
        if not isinstance(item, dict):
            return None
        url = str(item.get("url") or "")
        ghsa = url.rsplit("/", 1)[-1] if "/advisories/" in url else ""
        if ghsa:
            ids.add(ghsa)
        else:
            return None
    return ids


def resolve_advisory_ids(
    name: str,
    vulnerabilities: dict,
    seen: set[str] | None = None,
) -> set[str] | None:
    """Advisory ids reachable from a vulnerability entry, or None if unknown."""
    seen = set(seen or ())
    if name in seen:
        return set()
    seen.add(name)
    entry = vulnerabilities.get(name)
    if not isinstance(entry, dict):
        return None
    direct = _dict_advisory_ids(entry.get("via"))
    if direct is not None:
        return direct
    ids: set[str] = set()
    for item in entry.get("via") or []:
        if isinstance(item, dict):
            continue
        nested = resolve_advisory_ids(item, vulnerabilities, seen)
        if nested is None:
            return None
        ids |= nested
    return ids


def evaluate(report: dict, allowed: set[str]) -> tuple[list, list]:
    """Return ``(accepted, blocking)`` lists for high/critical vulnerabilities."""
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return [], [("audit-report", "error", ["missing vulnerabilities"])]
    accepted: list[tuple[str, list[str]]] = []
    blocking: list[tuple[str, str, list[str]]] = []
    for name, entry in vulnerabilities.items():
        if not isinstance(entry, dict):
            continue
        severity = entry.get("severity")
        if severity not in ("high", "critical"):
            continue
        ids = resolve_advisory_ids(name, vulnerabilities)
        if severity != "critical" and ids and ids <= allowed:
            accepted.append((name, sorted(ids)))
        else:
            blocking.append(
                (name, str(severity), sorted(ids) if ids else ["unattributed"])
            )
    return accepted, blocking


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", default=".", help="directory containing package.json")
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    args = parser.parse_args(argv)

    process = subprocess.run(
        ["npm", "audit", "--json"],
        cwd=args.cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError:
        print(
            f"npm audit did not return JSON (exit {process.returncode}): "
            f"{process.stdout[-500:]}",
            file=sys.stderr,
        )
        return 1

    accepted, blocking = evaluate(report, load_allowlist(args.allowlist))
    print(
        f"npm audit ({args.cwd}): high/critical accepted={len(accepted)} "
        f"blocking={len(blocking)}"
    )
    for name, ids in accepted:
        print(f"  accepted {name}: {', '.join(ids)}")
    for name, severity, ids in blocking:
        print(f"  BLOCKING {name}: {severity} ({', '.join(ids)})", file=sys.stderr)
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
