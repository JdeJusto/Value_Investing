"""Badge-count parsing and README updates without running pytest."""

from __future__ import annotations

from pathlib import Path

import scripts.update_badges as badges


def test_parse_passed_count_from_pytest_summary():
    output = "... 1728 passed, 2 skipped, 2 warnings in 160.08s"
    assert badges.parse_passed_count(output) == 1728


def test_parse_passed_count_uses_the_last_summary_match():
    output = "previous run: 120 passed\nnew run: 123 passed, 2 skipped"
    assert badges.parse_passed_count(output) == 123


def test_test_badge_regex_matches_expected_format():
    text = "![Tests](https://img.shields.io/badge/tests-1728%20passed-10A77A?style=for-the-badge)"
    match = badges.TEST_BADGE_RE.search(text)
    assert match is not None
    assert match.group(2) == "1728"


def test_parse_passed_count_rejects_missing_summary():
    try:
        badges.parse_passed_count("no pytest summary")
    except badges.BadgeError as exc:
        assert "N passed" in str(exc)
    else:
        raise AssertionError("expected a missing-summary error")


def test_check_exits_one_when_badge_is_stale(tmp_path, monkeypatch, capsys):
    (tmp_path / "README.md").write_text(
        "![Tests](https://img.shields.io/badge/tests-10%20passed-green)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(badges, "collect_test_count", lambda root: 12)
    assert badges.main(["--check"], root=tmp_path) == 1
    output = capsys.readouterr().out
    assert "badge count 10" in output
    assert "expected 12 passed" in output


def test_check_exits_zero_when_badge_is_current(tmp_path, monkeypatch, capsys):
    (tmp_path / "README.md").write_text(
        "![Tests](https://img.shields.io/badge/tests-12%20passed-green)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(badges, "collect_test_count", lambda root: 12)
    assert badges.main(["--check"], root=tmp_path) == 0
    assert "test badge is current (12 passed)" in capsys.readouterr().out


def test_in_place_update_writes_the_current_count_and_is_idempotent(
    tmp_path, monkeypatch
):
    readme = tmp_path / "README.md"
    readme.write_text(
        '<img src="https://img.shields.io/badge/tests-10%20passed-green" alt="10 tests passed">\n',
        encoding="utf-8",
    )
    spanish = tmp_path / "README.es.md"
    spanish.write_text(
        "![Tests](https://img.shields.io/badge/tests-8%20passed-blue)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(badges, "collect_test_count", lambda root: 12)

    assert badges.main([], root=tmp_path) == 0
    updated_readme = readme.read_text(encoding="utf-8")
    updated_spanish = spanish.read_text(encoding="utf-8")
    assert "tests-12%20passed" in updated_readme
    assert 'alt="12 tests passed"' in updated_readme
    assert "tests-12%20passed" in updated_spanish

    assert badges.main([], root=tmp_path) == 0
    assert readme.read_text(encoding="utf-8") == updated_readme
    assert spanish.read_text(encoding="utf-8") == updated_spanish


def test_in_place_update_leaves_optional_spanish_readme_without_badge(
    tmp_path, monkeypatch
):
    (tmp_path / "README.md").write_text(
        "![Tests](https://img.shields.io/badge/tests-10%20passed-green)\n",
        encoding="utf-8",
    )
    (tmp_path / "README.es.md").write_text("# README español\n", encoding="utf-8")
    monkeypatch.setattr(badges, "collect_test_count", lambda root: 11)
    assert badges.main([], root=tmp_path) == 0
    assert "tests-11%20passed" in (tmp_path / "README.md").read_text()
    assert (tmp_path / "README.es.md").read_text() == "# README español\n"


def test_update_badge_text_reports_number_of_badges_changed():
    text = (
        "![Tests](https://img.shields.io/badge/tests-1%20passed-green)\n"
        "![Tests](https://img.shields.io/badge/tests-2%20passed-blue)\n"
    )
    updated, count = badges.update_badge_text(text, 7)
    assert count == 2
    assert updated.count("tests-7%20passed") == 2


def test_release_script_updates_badges_before_version_commit():
    release_script = Path(__file__).resolve().parents[2] / "scripts" / "release.sh"
    text = release_script.read_text(encoding="utf-8")
    assert '"$PYTHON_BIN" -m scripts.update_badges' in text
    assert text.index("scripts.update_badges") < text.index(
        "Calculando la versión nueva"
    )
    assert "git add README.md" in text
    assert "[ -f README.es.md ] && git add README.es.md" in text
