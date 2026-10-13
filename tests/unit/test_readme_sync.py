"""README parity guard.

``README.md`` and ``README.es.md`` must stay structurally in sync. The tests
here compare heading levels and the badge set, not the prose: translations
differ by design, structure does not.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _headings(path: Path) -> list[tuple[int, str]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(#{1,3}) ", line)
        if m:
            out.append((len(m.group(1)), line.strip()))
    return out


def test_readme_and_translation_have_the_same_structure():
    en = _headings(ROOT / "README.md")
    es = _headings(ROOT / "README.es.md")
    # Compare only the heading LEVELS, not the text (translations
    # differ).
    assert [lvl for lvl, _ in en] == [lvl for lvl, _ in es], (
        "README.md and README.es.md have diverged. "
        f"EN levels: {[lvl for lvl, _ in en]}; "
        f"ES levels: {[lvl for lvl, _ in es]}"
    )


def test_readme_badges_match():
    def badges(p: Path) -> list[str]:
        text = p.read_text(encoding="utf-8")
        return sorted(set(re.findall(r"https://img\.shields\.io/[^\")\s]+", text)))

    en = badges(ROOT / "README.md")
    es = badges(ROOT / "README.es.md")
    assert en == es, (
        "Badge sets diverged between README.md and README.es.md.\n"
        f"EN-only: {set(en) - set(es)}\n"
        f"ES-only: {set(es) - set(en)}"
    )


def test_no_meta_capture_commentary():
    """The READMEs must not contain viewport/capture meta-commentary."""
    forbidden = [
        "browser viewport",
        "demo screenshots use pinned data",
        "captured at a",
        "1600 × 1000",
        "1600x1000",
    ]
    for name in ("README.md", "README.es.md"):
        text = (ROOT / name).read_text(encoding="utf-8").lower()
        for phrase in forbidden:
            assert phrase.lower() not in text, (
                f"{name} contains forbidden meta-commentary: {phrase!r}"
            )
