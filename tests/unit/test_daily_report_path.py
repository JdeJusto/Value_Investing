"""The report writer must not replace a healthy report with a degraded one."""

from __future__ import annotations

from datetime import date

from scripts.daily_workflow import _report_path


def test_degraded_run_preserves_the_existing_report(tmp_path):
    existing = tmp_path / "daily_2026-11-03.md"
    existing.write_text("healthy run", encoding="utf-8")

    path = _report_path(tmp_path, date(2026, 11, 3), degraded=True)

    assert path != existing
    assert path.name.startswith("daily_2026-11-03_")
    assert path.name.endswith("_partial.md")
    assert existing.read_text(encoding="utf-8") == "healthy run"


def test_healthy_rerun_keeps_the_canonical_path(tmp_path):
    existing = tmp_path / "daily_2026-11-03.md"
    existing.write_text("old run", encoding="utf-8")

    path = _report_path(tmp_path, date(2026, 11, 3), degraded=False)

    assert path == existing


def test_degraded_run_without_a_previous_report_uses_the_canonical_path(tmp_path):
    path = _report_path(tmp_path, date(2026, 11, 3), degraded=True)

    assert path == tmp_path / "daily_2026-11-03.md"
