#!/usr/bin/env python3
"""Benchmark the daily workflow phases (refresh / prices / analysis / total).

Runs ``daily_workflow`` as a subprocess for a given universe limit and
parses the wall-clock phase timings from its log output. Use it to compare
runs before and after a change:

    python -m scripts.benchmark_daily_workflow --limit 100 --workers 6
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _format_timings(phases: dict[str, float]) -> str:
    order = ("refresh", "prices", "analysis", "alerts", "report", "total")
    return " · ".join(
        f"{name} {phases[name]:.1f}s" for name in order if name in phases
    )


def run(limit: int, workers: int, no_update: bool, out_dir: str) -> dict[str, float]:
    cmd = [
        sys.executable,
        "-m",
        "scripts.daily_workflow",
        "--workers",
        str(workers),
        "--out",
        out_dir,
    ]
    if limit:
        cmd += ["--limit", str(limit)]
    if no_update:
        cmd += ["--no-update"]
    cmd += ["--verbose"]  # phase timings are INFO-level logs

    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    combined = proc.stdout + "\n" + proc.stderr
    phases: dict[str, float] = {}
    for line in combined.splitlines():
        if "[timing]" not in line:
            continue
        try:
            name, seconds = line.strip().split("[timing]")[1].strip().split(":")
            phases[name.strip()] = float(seconds.split("s")[0])
        except (ValueError, IndexError):
            continue
    if not phases:
        print(combined[-3000:], file=sys.stderr)
        raise SystemExit("no phase timings parsed — did the workflow fail?")
    return phases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--no-update", action="store_true", help="skip the SEC refresh phase"
    )
    parser.add_argument(
        "--out", default="/tmp/daily_benchmark", help="report/state output dir"
    )
    args = parser.parse_args()

    phases = run(args.limit, args.workers, args.no_update, args.out)
    universe = args.limit or "full"
    print(f"universe={universe} workers={args.workers}: "
          f"{_format_timings(phases)}")
    print(f"  total {phases.get('total', 0):.1f}s · prices "
          f"{phases.get('prices', 0):.1f}s · analysis "
          f"{phases.get('analysis', 0):.1f}s")


if __name__ == "__main__":
    main()