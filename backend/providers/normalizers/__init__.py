"""Normalizer registry: maps provider classes to their adapter.

Provider classes are imported lazily so that importing this package never
triggers heavy third-party SDK imports (yfinance, edgartools).
"""

from __future__ import annotations

from typing import Optional

from backend.domain.value_objects.financials_normalized import ProviderName
from backend.providers.normalizers.base import FinancialNormalizer
from backend.providers.normalizers.edgar_normalizer import EdgarNormalizer
from backend.providers.normalizers.yahoo_normalizer import YahooNormalizer


def _registry() -> dict[type, FinancialNormalizer]:
    from backend.providers.edgar.provider import EdgarProvider
    from backend.providers.yahoo.provider import YahooFinanceProvider

    return {
        YahooFinanceProvider: YahooNormalizer(),
        EdgarProvider: EdgarNormalizer(),
    }


def get_normalizer(provider: object) -> FinancialNormalizer | None:
    """Return the normalizer for a provider instance by its concrete type."""
    return _registry().get(type(provider))


def get_normalizer_by_source(source: ProviderName) -> FinancialNormalizer | None:
    """Return the normalizer registered for a provider name."""
    for normalizer in _registry().values():
        if normalizer.source == source:
            return normalizer
    return None
