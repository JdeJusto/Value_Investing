"""Unit tests for the shared ratio sanity guards (``ratio_guards``)."""

from __future__ import annotations

import pytest

from backend.methodologies.common.ratio_guards import (
    is_meaningful_ev_ebit,
    is_meaningful_fcf_yield,
    is_meaningful_pbv,
    is_meaningful_pe,
)


@pytest.mark.parametrize(
    "pe, expected",
    [
        (None, False),
        (0.0, False),
        (-1.0, False),
        (-195.78, False),  # losses: never a "cheap" multiple
        (0.01, True),
        (33.31, True),
        (100.0, True),
        (100.01, False),  # four-digit P/E is a denominator artifact
        (1583.74, False),
    ],
)
def test_is_meaningful_pe(pe, expected):
    assert is_meaningful_pe(pe) is expected


@pytest.mark.parametrize(
    "pbv, expected",
    [
        (None, False),
        (0.0, False),
        (-0.5, False),
        (0.1, True),
        (50.0, True),
        (50.01, False),
    ],
)
def test_is_meaningful_pbv(pbv, expected):
    assert is_meaningful_pbv(pbv) is expected


@pytest.mark.parametrize(
    "ev_ebit, expected",
    [
        (None, False),
        (0.0, False),
        (-12.0, False),  # negative EBIT is not a margin of safety
        (8.0, True),
        (100.0, True),
        (101.0, False),
    ],
)
def test_is_meaningful_ev_ebit(ev_ebit, expected):
    assert is_meaningful_ev_ebit(ev_ebit) is expected


@pytest.mark.parametrize(
    "yield_, expected",
    [
        (None, False),
        (-1.5, False),
        (-0.5, True),
        (0.0, True),
        (0.05, True),
        (1.0, True),
        (1.5, False),  # tiny market cap, not cash generation
    ],
)
def test_is_meaningful_fcf_yield(yield_, expected):
    assert is_meaningful_fcf_yield(yield_) is expected
