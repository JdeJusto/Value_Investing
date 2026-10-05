"""ui_format: dash/format helpers and the K/M/B/T abbreviation."""

from __future__ import annotations

from backend.services.ui_format import (
    DASH,
    abbreviate_number,
    abbreviate_value,
    fmt_or_dash,
)


def test_fmt_or_dash_keeps_none_as_dash():
    assert fmt_or_dash(None) == DASH
    assert fmt_or_dash(42.15) == "42.15"
    assert fmt_or_dash(0.2415, percent=True) == "24.15%"


# ---------------------------------------------------------------------------
# abbreviate_number (with the currency symbol)
# ---------------------------------------------------------------------------
def test_abbreviate_number_edge_cases():
    assert abbreviate_number(None) == "—"
    assert abbreviate_number(0) == "0"
    assert abbreviate_number(42) == "$42.00"
    assert abbreviate_number(999) == "$999.00"
    assert abbreviate_number(1_000) == "$1.00K"
    assert abbreviate_number(999_999) == "$1.00M"  # boundary rounding accepted
    assert abbreviate_number(1_000_000) == "$1.00M"
    assert abbreviate_number(1_000_000_000) == "$1.00B"
    assert abbreviate_number(416_161_000_000) == "$416.16B"
    assert abbreviate_number(3_870_000_000_000) == "$3.87T"
    assert abbreviate_number(4_500_000_000_000_000) == "$4.5e+15"


def test_abbreviate_number_negatives_use_parentheses():
    assert abbreviate_number(-19_001_000_000) == "($19.00B)"
    assert abbreviate_number(-42.15) == "($42.15)"
    assert abbreviate_number(-1_000) == "($1.00K)"


def test_abbreviate_number_units():
    assert abbreviate_number(14_776_353_000, "shares") == "14.78B sh"
    assert abbreviate_number(7.39, "USD/shares") == "$7.39"
    assert abbreviate_number(-7.39, "USD/shares") == "($7.39)"
    assert abbreviate_number(0.24, "percent") == "24.0%"  # not abbreviated
    assert abbreviate_number(0.1543, "pure") == "0.1543"  # not abbreviated
    assert abbreviate_number(1_500, "EUR") == "1.50K"  # unknown unit: no suffix


def test_abbreviate_number_promotes_the_unit_on_rounding():
    assert abbreviate_number(999_999) == "$1.00M"
    assert abbreviate_number(999_999_999) == "$1.00B"
    assert abbreviate_number(999_999_999_999) == "$1.00T"


# ---------------------------------------------------------------------------
# abbreviate_value (no currency symbol)
# ---------------------------------------------------------------------------
def test_abbreviate_value_omits_the_currency_symbol():
    assert abbreviate_value(416_161_000_000, "USD") == "416.16B"
    assert abbreviate_value(-19_001_000_000, "USD") == "(19.00B)"
    assert abbreviate_value(42.15, "USD") == "42.15"
    assert abbreviate_value(14_776_353_000, "shares") == "14.78B sh"
    assert abbreviate_value(0.24, "percent") == "24.0%"
    assert abbreviate_value(None, "USD") == "—"
    assert abbreviate_value(0, "USD") == "0"
