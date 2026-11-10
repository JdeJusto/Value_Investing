"""Shared helpers across the book methodologies and the not-from-canon DCF.

Currently a single module: :mod:`backend.methodologies.common.company_type`,
the company-typing logic (FINANCIAL / REIT / UTILITY / HYPER_GROWTH /
STANDARD / UNKNOWN) that used to live inside each methodology as a private
heuristic.
"""

from backend.methodologies.common.company_type import (
    CompanyType,
    company_flags,
    detect_company_type,
    is_financial,
    is_hyper_growth,
    is_reit,
    is_utility,
)

__all__ = [
    "CompanyType",
    "company_flags",
    "detect_company_type",
    "is_financial",
    "is_hyper_growth",
    "is_reit",
    "is_utility",
]
