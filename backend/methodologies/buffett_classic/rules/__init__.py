"""Buffett rule framework: categories, results and the 20 quantitative checks."""

from backend.methodologies.buffett_classic.rules.checks import (
    CATEGORIES,
    CHECKS,
    CHECKS_BY_ID,
    BuffettCheck,
    BuffettResult,
    run_checks,
)

__all__ = [
    "CATEGORIES",
    "CHECKS",
    "CHECKS_BY_ID",
    "BuffettCheck",
    "BuffettResult",
    "run_checks",
]
