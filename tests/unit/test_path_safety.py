"""Unit tests for the shared path-safety helpers (py/path-injection)."""

from __future__ import annotations

import pytest

from backend.services.path_safety import (
    UnsafePathComponent,
    safe_component,
    safe_join,
)


# ---------------------------------------------------------------------------
# safe_component: accepted values
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value",
    ["AAPL", "KO", "BRK-B", "BRK.B", "aapl", "RDS.A", "0", "ABCDE"],
)
def test_safe_component_accepts_plain_tickers(value):
    assert safe_component(value) == value


def test_safe_component_strips_surrounding_whitespace():
    assert safe_component("  AAPL  ") == "AAPL"


# ---------------------------------------------------------------------------
# safe_component: rejected values
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        ".",
        "..",
        "a/b",
        "a\\b",
        "../etc/passwd",
        "..\\..\\windows",
        "/absolute",
        "/etc/passwd",
        "AAPL\x00",
        "AAPL;rm",
        "AAPL\nKO",
        "AAPL" * 100,
    ],
)
def test_safe_component_rejects_unsafe_values(value):
    with pytest.raises(UnsafePathComponent):
        safe_component(value)


def test_safe_component_rejects_non_string():
    with pytest.raises(UnsafePathComponent):
        safe_component(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# safe_join
# ---------------------------------------------------------------------------
def test_safe_join_single_component_stays_inside_base(tmp_path):
    assert safe_join(tmp_path, "AAPL") == tmp_path / "AAPL"


def test_safe_join_multiple_components(tmp_path):
    assert safe_join(tmp_path, "a", "b") == tmp_path / "a" / "b"


def test_safe_join_filename_component_can_be_long(tmp_path):
    name = "consensus_" + "2024-12-31" + ".json"
    assert safe_join(tmp_path, name) == tmp_path / name


@pytest.mark.parametrize("bad", ["..", ".", "../etc/passwd", "a/b", "a\\b", "/etc"])
def test_safe_join_rejects_traversal_components(tmp_path, bad):
    with pytest.raises(UnsafePathComponent):
        safe_join(tmp_path, bad)


def test_safe_join_rejects_escape_through_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    base = tmp_path / "base"
    base.mkdir()
    (base / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePathComponent):
        safe_join(base, "link", "escaped.json")
