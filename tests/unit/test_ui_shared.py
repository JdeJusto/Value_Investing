"""Contract tests for ui._shared.render_html and the unsafe_allow_html guard."""

from pathlib import Path
from unittest.mock import patch

from ui._shared import render_html

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_render_html_does_not_raise():
    render_html("<b>x</b>")  # smoke: no exception


def test_render_html_delegates_to_st_markdown():
    with patch("ui._shared.st.markdown") as mock_markdown:
        render_html("<b>x</b>")
    mock_markdown.assert_called_once_with("<b>x</b>", unsafe_allow_html=True)


def test_no_unsafe_allow_html_outside_allowed_files():
    """Contract: unsafe_allow_html=True only lives in allowed files.

    Allowed:
      - ui/_shared.py        (this helper)
      - ui/theme/__init__.py (theming injection)
    """
    allowed = {
        _REPO_ROOT / "ui" / "_shared.py",
        _REPO_ROOT / "ui" / "theme" / "__init__.py",
    }
    offenders = []
    for py in (_REPO_ROOT / "ui").rglob("*.py"):
        if py in allowed:
            continue
        if "unsafe_allow_html" in py.read_text(encoding="utf-8"):
            offenders.append(str(py.relative_to(_REPO_ROOT)))
    assert offenders == [], (
        f"unsafe_allow_html found outside allowed files: {offenders}. "
        f"Use ui._shared.render_html instead."
    )
